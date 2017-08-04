from baselayer.app.handlers.base import BaseHandler
from baselayer.app.json_util import to_json

import tornado.web

import datetime
import jwt

# !!!
# This API call should **only be callable by logged in users**
# !!!

class SocketAuthTokenHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user_id = self.get_current_user(id_only=True)
        if user_id is None:
            raise RuntimeError('No current user while authenticating socket. '
                               'This should NEVER happen.')

        secret = self.cfg['app:secret-key']
        token = jwt.encode({
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15),
            'username': str(user_id),
            }, secret)
        self.success({'token': token})
