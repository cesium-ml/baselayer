import importlib
import time

import tornado.log
import tornado.ioloop
import requests

from baselayer.app.env import load_env, parser
from baselayer.log import make_log


parser.description = 'Launch app microservice'
parser.add_argument('-p', '--process', type=int,
                    help='Process number, when multiple server processes are used.'
                         ' This number gets added to the app port.')
env, cfg = load_env()

log = make_log(f'app_{env.process or 0}')

# We import these later, otherwise them calling load_env interferes
# with argument parsing
from baselayer.app.app_server import (
    handlers as baselayer_handlers,
    settings as baselayer_settings,
)  # noqa: E402

app_factory = cfg['app.factory']
baselayer_settings['cookie_secret'] = cfg['app.secret_key']
baselayer_settings['autoreload'] = env.debug
# if env.debug:
#     import logging
#     logging.basicConfig()
#     logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

module, app_factory = app_factory.rsplit('.', 1)
app_factory = getattr(importlib.import_module(module), app_factory)

app = app_factory(cfg, baselayer_handlers, baselayer_settings,
                  process=env.process if env.process else 0,
                  env=env)
app.cfg = cfg


def migrated_db(migration_manager_port):
    port = migration_manager_port
    try:
        r = requests.get(f'http://localhost:{port}')
        status = r.json()
    except requests.exceptions.RequestException:
        log(f'Could not connect to migration manager on port [{port}]')
        return None

    return status["migrated"]


# Before serving, ask migration_manager whether the DB is ready
log('Verifying database migration status')
port = cfg['ports.migration_manager']
timeout = 1
while not migrated_db(port):
    log(f'Database not migrated, or could not verify; trying again in {timeout}s')
    time.sleep(timeout)
    timeout = max(timeout * 2, 30)

port = cfg['ports.app_internal'] + (env.process or 0)
app.listen(port, xheaders=True)

log(f'Listening on port {port}')
tornado.ioloop.IOLoop.current().start()
