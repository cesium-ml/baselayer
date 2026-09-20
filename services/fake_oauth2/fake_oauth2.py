import time
import uuid

import tornado.ioloop
import tornado.web
from tornado.httputil import url_concat
from tornado.web import RequestHandler

from baselayer.app.env import load_env
from baselayer.log import make_log


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
log = make_log("fake_oauth2")

if not cfg["server.auth.debug_login"]:
    log("server.auth.debug_login is false: not serving the fake OAuth2 endpoints")
    # Idle rather than exit so supervisor doesn't restart-loop.
    while True:
        time.sleep(3600)

handlers = [
    ("/fakeoauth2/auth", FakeGoogleOAuth2AuthHandler),
    ("/fakeoauth2/token", FakeGoogleOAuth2TokenHandler),
]
app = tornado.web.Application(handlers)
app.listen(cfg["ports.fake_oauth"])

tornado.ioloop.IOLoop.current().start()
