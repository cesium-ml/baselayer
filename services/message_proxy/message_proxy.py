# http://zguide.zeromq.org/page:all#The-Dynamic-Discovery-Problem

import zmq

from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()

log = make_log("message_proxy")

IN = cfg["ports.websocket_path_in"]
OUT = cfg["ports.websocket_path_out"]


def bind_endpoint(endpoint):
    """Convert a ZMQ *connect* endpoint into the matching *bind* endpoint.

    ipc:// binds and connects to the same path (returned unchanged). tcp://
    must bind all interfaces, so the host is replaced with the wildcard ``*``
    while the port is kept (tcp://message_proxy:64002 -> tcp://*:64002).
    """
    if endpoint.startswith("tcp://"):
        port = endpoint.rsplit(":", 1)[-1]
        return f"tcp://*:{port}"
    return endpoint


IN_BIND = bind_endpoint(IN)
OUT_BIND = bind_endpoint(OUT)

context = zmq.Context()

feed_in = context.socket(zmq.PULL)
feed_in.bind(IN_BIND)

feed_out = context.socket(zmq.PUB)
feed_out.bind(OUT_BIND)

log(f"Forwarding messages between {IN_BIND} and {OUT_BIND}")
zmq.proxy(feed_in, feed_out)
