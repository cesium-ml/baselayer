import uuid

import tornado.ioloop
import tornado.web
from baselayer.app.env import load_env
from tornado.httputil import url_concat
from tornado.web import RequestHandler


class FakeGoogleOAuth2AuthHandler(RequestHandler):
    def get(self):
        # issue a fake auth code and redirect to redirect_uri
        code = "fake-authorization-code"
        self.redirect(
            url_concat(
                self.get_argument("redirect_uri"),
                dict(code=code, state=self.get_argument("state")),
            )
        )


class FakeGoogleOAuth2TokenHandler(RequestHandler):
    def post(self):
        self.get_argument("code") == "fake-authorization-code"

        fake_token = str(uuid.uuid4())
        self.write({"access_token": fake_token, "expires_in": "never-expires"})


env, cfg = load_env()

handlers = [
    ("/fakeoauth2/auth", FakeGoogleOAuth2AuthHandler),
    ("/fakeoauth2/token", FakeGoogleOAuth2TokenHandler),
]
app = tornado.web.Application(handlers)
app.listen(cfg["ports.fake_oauth"])

tornado.ioloop.IOLoop.current().start()
