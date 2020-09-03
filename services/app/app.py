import importlib

from baselayer.app.env import load_env, parser
from baselayer.log import make_log

import tornado.log
import tornado.ioloop


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

app = app_factory(cfg, baselayer_handlers, baselayer_settings)
app.cfg = cfg

port = cfg['ports.app_internal'] + (env.process or 0)
app.listen(port)

log(f'Listening on port {port}')
tornado.ioloop.IOLoop.current().start()
