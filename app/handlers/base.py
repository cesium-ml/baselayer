import tornado.escape
from sqlalchemy.orm import joinedload
from json.decoder import JSONDecodeError

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

    def get_current_user(self):
        """Get currently logged in user.

        The currently logged in user_id is stored in a secure cookie
        by Python Social Auth.
        """
        # This cookie is set by Python Social Auth's
        # BaseHandler:
        # https://github.com/python-social-auth/social-app-tornado/blob/master/social_tornado/handlers.py
        user_id = self.get_secure_cookie('user_id')
        if user_id is None:
            return None
        else:
            return User.query\
                       .options(joinedload('acls'))\
                       .get(int(user_id))

    def push(self, action, payload={}):
        """Broadcast a message to current frontend user.

        Parameters
        ----------
        action : str
            Name of frontend action to perform after API success.  This action
            is sent to the frontend over WebSocket.
        payload : dict, optional
            Action payload.  This data accompanies the action string
            to the frontend.
        """
        # Don't push messages if current user is a token
        if hasattr(self.current_user, 'username'):
            self.flow.push(self.current_user.username, action, payload)

    def push_all(self, action, payload={}):
        """Broadcast a message to all frontend users.

        Use this functionality with care for two reasons:

        - It emits many messages, and if those messages trigger a response from
          frontends, it can result in many incoming API requests
        - Any information included in the message will be seen by everyone; and
          everyone will know it was sent.  Do not, e.g., send around a message
          saying "secret object XYZ was updated; fetch the latest version".
          Even though the user won't be able to fetch the object, they'll
          know that it exists, and that it was modified.

        Parameters
        ----------
        action : str
            Name of frontend action to perform after API success.  This action
            is sent to the frontend over WebSocket.
        payload : dict, optional
            Action payload.  This data accompanies the action string
            to the frontend.
        """
        self.flow.push('*', action, payload=payload)

    def get_json(self):
        if len(self.request.body) == 0:
            return {}
        try:
            return tornado.escape.json_decode(self.request.body)
        except JSONDecodeError:
            raise Exception(
                f'JSON decode of request body failed on {self.request.uri}.'
                ' Please ensure all requests are of type application/json.')

    def on_finish(self):
        DBSession.remove()
        return super(BaseHandler, self).on_finish()

    def error(self, message, data={}, status=400):
        """Push an error message to the frontend via WebSocket connection.

        Parameters
        ----------
        message : str
            Description of the error.
        data : dict, optional
            Any data to be included with error message.
        status : int, optional
            HTTP status code.  Defaults to 400 (bad request).
            See https://www.restapitutorial.com/httpstatuscodes.html for a full
            list.
        """
        print('! App Error:', message)

        self.set_status(status)
        self.write({
            "status": "error",
            "message": message,
            "data": data
            })

    def action(self, action, payload={}):
        """Push an action to the frontend via WebSocket connection.

        Parameters
        ----------
        action : str
            Name of frontend action to perform after API success.  This action
            is sent to the frontend over WebSocket.
        payload : dict, optional
            Action payload.  This data accompanies the action string
            to the frontend.
        """
        self.push(action, payload)

    def success(self, data={}, action=None, payload={}, status=200):
        """Write data and send actions on API success.

        Parameters
        ----------
        data : dict, optional
            The JSON returned by the API call.
        action : str, optional
            Name of frontend action to perform after API success.  This action
            is sent to the frontend over WebSocket.
        payload : dict, optional
            Action payload.  This data accompanies the action string
            to the frontend.
        status : int, optional
            HTTP status code.  Defaults to 200 (OK).
            See https://www.restapitutorial.com/httpstatuscodes.html for a full
            list.
        """
        if action is not None:
            self.action(action, payload)

        self.set_status(status)
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
        PORT_SCHEDULER = self.cfg['ports.dask']

        from distributed import Client
        client = await Client('{}:{}'.format(IP, PORT_SCHEDULER),
                              asynchronous=True)

        return client

    def push_notification(self, note, notification_type='info'):
        self.push(action='baselayer/SHOW_NOTIFICATION',
                  payload={'note': note,
                           'type': notification_type})
