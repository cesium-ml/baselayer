import os
import shutil
import subprocess
import time

import tornado.ioloop
import tornado.web
from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()
log = make_log("migration_manager")


conf_files = env.config
conf_flags = ["-x", f'config={":".join(conf_files)}'] if conf_files else []


class timeout_cache:
    def __init__(self, timeout):
        self.timeout = timeout
        self.lastrun = 0
        self.cache = None
        self.func = None

    def __call__(self, f):
        self.func = f
        return self.wrapped

    def wrapped(self, *args, **kwargs):
        tic = self.lastrun
        toc = time.time()
        if (toc - tic) > self.timeout or self.cache is None:
            self.lastrun = toc
            self.cache = self.func(*args, **kwargs)

        return self.cache


def _alembic(*options):
    path_env = os.environ.copy()
    path_env["PYTHONPATH"] = "."

    p = subprocess.Popen(
        ["alembic"] + conf_flags + list(options),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=path_env,
    )

    output, error = p.communicate()
    return p, output, error


def migrations_exist():
    if not os.path.isdir("./alembic/versions"):
        log("No migrations present; continuing")
        return False

    if shutil.which("alembic") is None:
        log("`alembic` executable not found; continuing")
        return False

    return True


def migrate():
    path_env = os.environ.copy()
    path_env["PYTHONPATH"] = "."

    cmd = ["alembic"] + conf_flags + ["upgrade", "head"]
    log(f'Attempting migration: {" ".join(cmd)}')
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, env=path_env)

    output, error = p.communicate()
    for line in error.decode("utf-8").split("\n"):
        log(line)

    if p.returncode != 0:
        log("Migration failed")
    else:
        log("Migration succeeded")


@timeout_cache(timeout=10)
def migration_status():
    if not migrations_exist():
        # No migrations present, continue as usual
        return True

    p, output, error = _alembic("current", "--verbose")

    if p.returncode != 0:
        log("Alembic returned an error; aborting")
        log(output.decode("utf-8"))
        return False

    status = output.decode("utf-8").strip().split("\n")
    status = [line for line in status if line.startswith("Rev: ")]
    if not status:
        log("Database not stamped: assuming migrations not in use; continuing")
        return True

    if status[0].endswith("(head)"):
        log("Database is up to date")
        return True

    log("Database is not migrated")
    return False


class MainHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", "application/json")

    def get(self):
        self.write({"migrated": migration_status()})


def make_app():
    return tornado.web.Application(
        [
            (r"/", MainHandler),
        ]
    )


if __name__ == "__main__":
    try:
        if migrations_exist() and not migration_status():
            # Attempt migration on startup
            migrate()
    except Exception as e:
        log(f"Uncaught exception: {e}")

    migration_manager = make_app()

    port = cfg["ports.migration_manager"]
    migration_manager.listen(port)
    log(f"Listening on port {port}")
    tornado.ioloop.IOLoop.current().start()
