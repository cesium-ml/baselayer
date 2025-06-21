import datetime

import jwt
import tornado.web
from baselayer.app.handlers.base import BaseHandler

# !!!
# This API call should **only be callable by logged in users**
# !!!


class SocketAuthTokenHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user = self.current_user
        if user is None:
            raise RuntimeError(
                "No current user while authenticating socket. "
                "This should NEVER happen."
            )

        secret = self.cfg["app.secret_key"]
        token = jwt.encode(
            {
                "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=15),
                "user_id": str(user.id),
            },
            secret,
        )
        self.success({"token": token})
