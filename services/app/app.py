import gc
import importlib
import os
import signal
import sys
import time

import requests
import tornado.ioloop

from baselayer.app.env import load_env, parser
from baselayer.log import make_log

parser.description = "Launch app microservice"
parser.add_argument(
    "-p",
    "--process",
    type=int,
    help="Process number, when multiple server processes are used."
    " This number gets added to the app port.",
)
env, cfg = load_env()

log = make_log("app" if env.process is None else f"app_{env.process}")

# We import these later, otherwise them calling load_env interferes
# with argument parsing
from baselayer.app.app_server import handlers as baselayer_handlers  # noqa: E402
from baselayer.app.app_server import settings as baselayer_settings  # noqa: E402

baselayer_settings["cookie_secret"] = cfg["app.secret_key"]
baselayer_settings["autoreload"] = env.debug


def migrated_db(port):
    try:
        return requests.get(f"http://localhost:{port}").json()["migrated"]
    except requests.exceptions.RequestException:
        return None


def serve(process):
    module, factory = cfg["app.factory"].rsplit(".", 1)
    app = getattr(importlib.import_module(module), factory)(
        cfg,
        baselayer_handlers,
        baselayer_settings,
        process=process,
        env=env,
    )
    app.cfg = cfg

    app_port = cfg["ports.app_internal"] + process
    address = "127.0.0.1"
    app.listen(app_port, xheaders=True, address=address)

    make_log(f"app_{process}")(f"Listening on {address}:{app_port}")
    tornado.ioloop.IOLoop.current().start()


def fork_worker(process):
    sys.stdout.flush()
    pid = os.fork()
    if pid:
        return pid
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    logfile = os.open(
        f"log/app_{process:02d}.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
    )
    os.dup2(logfile, sys.stdout.fileno())
    os.dup2(logfile, sys.stderr.fileno())
    os.close(logfile)
    try:
        serve(process)
    finally:
        os._exit(1)


def supervise(n_processes):
    workers = {fork_worker(process): process for process in range(n_processes)}

    def terminate(signum, frame):
        for pid in workers:
            os.kill(pid, signal.SIGTERM)
        sys.exit(0)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)

    while True:
        pid, status = os.wait()
        process = workers.pop(pid, None)
        if process is None:
            continue
        log(f"Worker {process} exited with status {status}; restarting")
        time.sleep(1)
        workers[fork_worker(process)] = process


log("Verifying database migration status")
port = cfg["ports.migration_manager"]
timeout = 1
while not migrated_db(port):
    if timeout in (1, 30):
        log(f"Database not migrated, or not reachable on port [{port}]; retrying")
    time.sleep(timeout)
    timeout = min(timeout * 2, 30)


if env.process is None and cfg["server.prefork"]:
    # The app is imported by now, so the workers inherit it copy-on-write.
    gc.freeze()
    supervise(cfg["server.processes"])
else:
    serve(env.process or 0)
