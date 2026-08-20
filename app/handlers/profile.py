import tornado.web

from baselayer.app.handlers.base import BaseHandler
from baselayer.app.models import Token


class ProfileHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user = self.current_user
        if isinstance(user, Token):
            user = user.created_by
        return self.success({"username": user.username})


class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.clear_cookie("user_id")
        self.redirect("/")
