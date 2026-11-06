import os
import shutil
import subprocess

import tornado.ioloop
import tornado.web

from baselayer.app.env import load_env
from baselayer.app.models import init_db
from baselayer.log import make_log

env, cfg = load_env()
log = make_log("migration_manager")


conf_files = env.config
conf_flags = ["-x", f"config={':'.join(conf_files)}"] if conf_files else []

migrated = False


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
    log(f"Attempting migration: {' '.join(cmd)}")
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, env=path_env)

    output, error = p.communicate()
    for line in error.decode("utf-8").split("\n"):
        log(line)

    if p.returncode != 0:
        log("Migration failed")
    else:
        log("Migration succeeded")


def check_migration_status():
    if not migrations_exist():
        # No migrations present, continue as usual
        return True

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
        engine = init_db(**{**cfg["database"], "pooler": None})
        try:
            with engine.connect() as conn:
                current = set(MigrationContext.configure(conn).get_current_heads())
        finally:
            engine.dispose()
    except Exception as e:
        log(f"Could not read the migration status; aborting: {e}")
        return False

    if not current:
        log("Database not stamped: assuming migrations not in use; continuing")
        return True

    if current == heads:
        log("Database is up to date")
        return True

    log("Database is not migrated")
    return False


def migration_status():
    global migrated
    if not migrated:
        migrated = check_migration_status()
    return migrated


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
