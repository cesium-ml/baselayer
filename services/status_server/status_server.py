import tornado.ioloop
import tornado.web

from baselayer.app.env import load_env
from baselayer.log import make_log

env, cfg = load_env()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("<h2>SkyPortal is being provisioned</h2>")

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
    ])

if __name__ == "__main__":
    app = make_app()
    app.listen(cfg['ports.status'])
    tornado.ioloop.IOLoop.current().start()
