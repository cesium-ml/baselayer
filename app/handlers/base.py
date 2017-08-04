import tornado.escape
import tornado.ioloop
from sqlalchemy.orm.exc import NoResultFound

# The Python Social Auth base handler gives us:
#   user_id, get_current_user, login_user
#
# `get_current_user` is needed by tornado.authentication,
# and provides a cached version, `current_user`, that should
# be used to look up the logged in user.
from social_tornado.handlers import BaseHandler as PSABaseHandler

from ..models import DBSession, User
from ..json_util import to_json
from ..flow import Flow

import time


class BaseHandler(PSABaseHandler):
    def prepare(self):
        self.cfg = self.application.cfg
        self.flow = Flow()

        # Remove slash prefixes from arguments
        if self.path_args and self.path_args[0] is not None:
            self.path_args = [arg.lstrip('/') for arg in self.path_args]
            self.path_args = [arg if (arg != '') else None
                                  for arg in self.path_args]

        # If there are no arguments, make it explicit, otherwise
        # get / post / put / delete all have to accept an optional kwd argument
        if len(self.path_args) == 1 and self.path_args[0] is None:
            self.path_args = []

        # TODO Refactor to be a context manager or utility function
        N = 5
        for i in range(1, N + 1):
            try:
                assert DBSession.session_factory.kw['bind'] is not None
            except Exception as e:
                if (i == N):
                    raise e
                else:
                    print('Error connecting to database, sleeping for a while')
                    time.sleep(5)

        return super(BaseHandler, self).prepare()

    def get_current_user(self, id_only=False):
        """Get currently logged in user.

        The currently logged in user_id is stored in a secure cookie
        by Python Social Auth, iff the server is in multi_user mode.
        Otherwise, we always return the test user.

        Parameters
        ----------
        id_only : bool
            Whether the full user or only the user_id should be returned.

        Returns
        -------
        user or user_id : str or int
            Username or id, depending on `id_only`.

        """
        if not self.cfg['server:multi_user']:
            username = 'testuser@gmail.com'
            try:
                user = User.query.filter(User.username == username).one()
            except NoResultFound:
                user = User(username=username)
                DBSession.add(user)
                DBSession().commit()

            if id_only:
                return int(user.id)
            else:
                return user
        else:
            # This cookie is set by Python Social Auth's
            # BaseHandler:
            # https://github.com/python-social-auth/social-app-tornado/blob/master/social_tornado/handlers.py
            user_id = self.get_secure_cookie('user_id')
            if user_id is None:
                return None
            else:
                # We duplicate the `id_only` check here,
                # because we do not want to make a query into the database
                # unnecessarily each time the current user_id is requested.
                #
                # E.g., this happens frequently whenever websocket messages
                # need to be passed around.
                if id_only:
                    return int(user_id)
                else:
                    return User.query.get(int(user_id))

    def push(self, action, payload={}):
        user_id = str(self.get_current_user(id_only=True))
        if not user_id:
            raise RuntimeError("Cannot push messages unless user is logged in")
        else:
            self.flow.push(user_id, action, payload)

    def get_json(self):
        return tornado.escape.json_decode(self.request.body)

    def on_finish(self):
        DBSession.remove()
        return super(BaseHandler, self).on_finish()

    def error(self, message, data={}):
        print('! App Error:', message)

        self.set_status(200)
        self.write({
            "status": "error",
            "message": message,
            "data": data
            })

    def action(self, action, payload={}):
        self.push(action, payload)

    def success(self, data={}, action=None, payload={}):
        if action is not None:
            self.action(action, payload)

        self.write(to_json(
            {
                "status": "success",
                "data": data
            }))

    def write_error(self, status_code, exc_info=None):
        if exc_info is not None:
            err_cls, err, traceback = exc_info
        else:
            err = 'An unknown error occurred'

        self.error(str(err))

    async def _get_client(self):
        IP = '127.0.0.1'
        PORT = 63000
        PORT_SCHEDULER = 63500

        from distributed import Client
        client = await Client('{}:{}'.format(IP, PORT_SCHEDULER),
                              asynchronous=True)

        return client
