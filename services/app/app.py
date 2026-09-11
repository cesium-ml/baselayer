import importlib
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

log = make_log(f"app_{env.process or 0}")

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


log("Verifying database migration status")
port = cfg["ports.migration_manager"]
timeout = 1
while not migrated_db(port):
    if timeout in (1, 30):
        log(f"Database not migrated, or not reachable on port [{port}]; retrying")
    time.sleep(timeout)
    timeout = min(timeout * 2, 30)


module, factory = cfg["app.factory"].rsplit(".", 1)
app = getattr(importlib.import_module(module), factory)(
    cfg,
    baselayer_handlers,
    baselayer_settings,
    process=env.process or 0,
    env=env,
)
app.cfg = cfg

app_port = cfg["ports.app_internal"] + (env.process or 0)
address = "127.0.0.1"
app.listen(app_port, xheaders=True, address=address)

log(f"Listening on {address}:{app_port}")
tornado.ioloop.IOLoop.current().start()
