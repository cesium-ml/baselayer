import tornado.ioloop
import tornado.web

from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_status(503)
        self.write(f"<h2>{cfg['app.title']} is being provisioned</h2>")


class MainAPIHandler(tornado.web.RequestHandler):
    def get(self, args):
        self.set_header("Content-Type", "application/json")
        self.set_status(503)
        self.write({
            "status": "error",
            "message": "System provisioning",
        })


def make_app():
    return tornado.web.Application([
        (r"/api(/.*)?", MainAPIHandler),
        (r".*", MainHandler),
    ])


if __name__ == "__main__":
    app = make_app()
    app.listen(cfg['ports.status'])
    tornado.ioloop.IOLoop.current().start()
