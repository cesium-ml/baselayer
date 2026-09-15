import os

import tornado.web


class HealthHandler(tornado.web.RequestHandler):
    """Liveness probe for a single app worker.

    Not a BaseHandler: we want this to be minimal—no DB etc.

    HEAD is served so that probes stay out of the nginx access log.
    """

    def get(self):
        self.set_header("Cache-Control", "no-store")
        self.write({"status": "success", "data": {"pid": os.getpid()}})

    head = get
