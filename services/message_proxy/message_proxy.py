# http://zguide.zeromq.org/page:all#The-Dynamic-Discovery-Problem

import zmq

from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()

log = make_log("message_proxy")

BIND = cfg["hosts.message_bus_bind"]
IN = f"tcp://{BIND}:{cfg['ports.message_bus_receive']}"
OUT = f"tcp://{BIND}:{cfg['ports.message_bus_publish']}"

context = zmq.Context()

feed_in = context.socket(zmq.PULL)
feed_in.bind(IN)

feed_out = context.socket(zmq.PUB)
feed_out.bind(OUT)

log(f"Forwarding messages between {IN} and {OUT}")
zmq.proxy(feed_in, feed_out)
