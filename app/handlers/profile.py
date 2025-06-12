import tornado.web
from baselayer.app.handlers.base import BaseHandler


class ProfileHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        return self.success({"username": self.current_user.username})


class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.clear_cookie("user_id")
        self.redirect("/")
