import tornado.ioloop
import tornado.web
from baselayer.app.env import load_env

env, cfg = load_env()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_status(503)
        self.write(f"<h2>{cfg['app.title']} is being provisioned</h2>")
        self.write(
            "<p>Sysadmins can run <code>make monitor</code> on the server to see how that is progressing."
        )
        self.write("<p>System logs are in <code>./log/app_*.log</code></p>")


class MainAPIHandler(tornado.web.RequestHandler):
    def get(self, args):
        self.set_header("Content-Type", "application/json")
        self.set_status(503)
        self.write(
            {
                "status": "error",
                "message": "System provisioning",
            }
        )


def make_app():
    return tornado.web.Application(
        [
            (r"/api(/.*)?", MainAPIHandler),
            (r".*", MainHandler),
        ]
    )


if __name__ == "__main__":
    app = make_app()
    app.listen(cfg["ports.status"])
    tornado.ioloop.IOLoop.current().start()
