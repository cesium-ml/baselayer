import importlib
import argparse

from zmq.eventloop import ioloop

from baselayer.app.app_server import (handlers as baselayer_handlers,
                                      settings as baselayer_settings)
from baselayer.app.env import load_env

import tornado.log

ioloop.install()

env, cfg = load_env()

app_factory = cfg['app:factory']
baselayer_settings['cookie_secret'] = cfg['app:secret-key']
baselayer_settings['autoreload'] = env.debug
if env.debug:
    import logging
    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

module, app_factory = app_factory.rsplit('.', 1)
app_factory = getattr(importlib.import_module(module), app_factory)

app = app_factory(cfg, baselayer_handlers, baselayer_settings)
app.cfg = cfg

app.listen(cfg['ports:app_internal'])

ioloop.IOLoop.current().start()
