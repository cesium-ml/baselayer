# http://zguide.zeromq.org/page:all#The-Dynamic-Discovery-Problem

import zmq
from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()

log = make_log("message_proxy")

IN = cfg["ports.websocket_path_in"]
OUT = cfg["ports.websocket_path_out"]

context = zmq.Context()

feed_in = context.socket(zmq.PULL)
feed_in.bind(IN)

feed_out = context.socket(zmq.PUB)
feed_out.bind(OUT)

log(f"Forwarding messages between {IN} and {OUT}")
zmq.proxy(feed_in, feed_out)
