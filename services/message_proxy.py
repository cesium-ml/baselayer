# http://zguide.zeromq.org/page:all#The-Dynamic-Discovery-Problem

import zmq

from baselayer.app.env import load_env

env, cfg = load_env()

IN = cfg['ports:websocket_path_in']
OUT = cfg['ports:websocket_path_out']

context = zmq.Context()

feed_in = context.socket(zmq.PULL)
feed_in.bind(IN)

feed_out = context.socket(zmq.PUB)
feed_out.bind(OUT)

print('[message_proxy] Forwarding messages between {} and {}'.format(IN, OUT))
zmq.proxy(feed_in, feed_out)
