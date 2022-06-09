import inspect
import time
import uuid
from contextlib import contextmanager
from json.decoder import JSONDecodeError

import social_tornado.handlers as psa_handlers

# The Python Social Auth base handler gives us:
#   user_id, get_current_user, login_user
#
# `get_current_user` is needed by tornado.authentication,
# and provides a cached version, `current_user`, that should
# be used to look up the logged in user.
import sqlalchemy
import tornado.escape
from tornado.log import app_log
from tornado.web import RequestHandler

from ...log import make_log

# Initialize PSA tornado models
from .. import psa  # noqa
from ..custom_exceptions import AccessError
from ..env import load_env
from ..flow import Flow
from ..json_util import to_json
from ..models import DBSession, User, VerifiedSession, bulk_verify, session_context_id

env, cfg = load_env()
log = make_log("basehandler")

# Monkey-patch Python Social Auth's base handler
#
# See
# https://github.com/python-social-auth/social-app-tornado/blob/master/social_tornado/handlers.py
# for the original
#
# Python Social Auth documentation:
# https://python-social-auth.readthedocs.io/en/latest/backends/implementation.html#auth-apis


class NoValue:
    pass


class PSABaseHandler(RequestHandler):
    """
    Mixin used by Python Social Auth
    """

    def user_id(self):
        return self.get_secure_cookie("user_id")

    def get_current_user(self):
        if self.user_id() is None:
            return
        user_id = int(self.user_id())
        oauth_uid = self.get_secure_cookie("user_oauth_uid")
        if user_id and oauth_uid:
            with DBSession() as session:
                user = session.scalars(
                    sqlalchemy.select(User).where(User.id == user_id)
                ).first()
                if user is None:
                    return
                sa = user.social_auth.first()
                if sa is None:
                    # No SocialAuth entry; probably machine generated user
                    return user
                if sa.uid.encode("utf-8") == oauth_uid:
                    return user

    def login_user(self, user):
        self.set_secure_cookie("user_id", str(user.id))
        sa = user.social_auth.first()
        if sa is not None:
            self.set_secure_cookie("user_oauth_uid", sa.uid)

    def write_error(self, status_code, exc_info=None):
        if exc_info is not None:
            err_cls, err, traceback = exc_info
        else:
            err = "An unknown error occurred"
        self.render("loginerror.html", app=cfg["app"], error_message=str(err))

    def log_exception(self, typ=None, value=None, tb=None):
        expected_exceptions = [
            "Authentication Error:",
            "User account expired",
            "Credentials malformed",
            "Method Not Allowed",
            "Unauthorized",
        ]
        v_str = str(value)
        if any(exception in v_str for exception in expected_exceptions):
            log(f"Error response returned by [{self.request.path}]: [{v_str}]")
        else:
            app_log.error(
                "Uncaught exception %s\n%r",
                self._request_summary(),
                self.request,
                exc_info=(typ, value, tb),
            )

    def on_finish(self):
        DBSession.remove()


# Monkey-patch in each method of social_tornado.handlers.BaseHandler
for (name, fn) in inspect.getmembers(PSABaseHandler, predicate=inspect.isfunction):
    setattr(psa_handlers.BaseHandler, name, fn)


class BaseHandler(PSABaseHandler):
    @contextmanager
    def Session(self):
        """
        Generate a scoped session that also has knowledge
        of the current user, so when commit() is called on it
        it will also verify that all rows being committed
        are accessible to the user.
        The current user is taken from the handler's `current_user`.
        This is a shortcut method to `models.Session`
        that saves the need to manually input the user object.

        Parameters
        ----------
        verify : boolean
            if True (default), will call the functions
            `verify()` and whenever `commit()` is called.

        Returns
        -------
        A scoped session object that can be used in a context
        manager to access the database. If auto verify is enabled,
        will use the current user given to apply verification
        before every commit.

        """
        with VerifiedSession(self.current_user) as session:
            # must merge the user object with the current session
            # ref: https://docs.sqlalchemy.org/en/14/orm/session_basics.html#adding-new-or-existing-items
            session.add(self.current_user)
            yield session

    def verify_permissions(self):
        """Check that the current user has permission to create, read,
        update, or delete rows that are present in the session. If not,
        raise an AccessError (causing the transaction to fail and the API to
        respond with 401).
        """

        # get items to be inserted
        new_rows = [row for row in DBSession().new]

        # get items to be updated
        updated_rows = [
            row for row in DBSession().dirty if DBSession().is_modified(row)
        ]

        # get items to be deleted
        deleted_rows = [row for row in DBSession().deleted]

        # get items that were read
        read_rows = [
            row
            for row in set(DBSession().identity_map.values())
            - (set(updated_rows) | set(new_rows) | set(deleted_rows))
        ]

        # need to check delete permissions before flushing, as deleted records
        # are not present in the transaction after flush (thus can't be used in
        # joins). Read permissions can be checked here or below as they do not
        # change on flush.
        for mode, collection in zip(
            ["read", "update", "delete"],
            [read_rows, updated_rows, deleted_rows],
        ):
            bulk_verify(mode, collection, self.current_user)

        # update transaction state in DB, but don't commit yet. this updates
        # or adds rows in the database and uses their new state in joins,
        # for permissions checking purposes.
        DBSession().flush()
        bulk_verify("create", new_rows, self.current_user)

    def verify_and_commit(self):
        """Verify permissions on the current database session and commit if
        successful, otherwise raise an AccessError.
        """
        self.verify_permissions()
        DBSession().commit()

    def prepare(self):
        self.cfg = self.application.cfg
        self.flow = Flow()
        session_context_id.set(uuid.uuid4().hex)

        # Remove slash prefixes from arguments
        if self.path_args:
            self.path_args = [
                arg.lstrip("/") if arg is not None else None for arg in self.path_args
            ]
            self.path_args = [arg if (arg != "") else None for arg in self.path_args]

        # If there are no arguments, make it explicit, otherwise
        # get / post / put / delete all have to accept an optional kwd argument
        if len(self.path_args) == 1 and self.path_args[0] is None:
            self.path_args = []

        # TODO Refactor to be a context manager or utility function
        N = 5
        for i in range(1, N + 1):
            try:
                assert DBSession.session_factory.kw["bind"] is not None
            except Exception as e:
                if i == N:
                    raise e
                else:
                    log("Error connecting to database, sleeping for a while")
                    time.sleep(5)

        return super().prepare()

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
        if hasattr(self.current_user, "username"):
            self.flow.push(self.current_user.id, action, payload)

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
        self.flow.push("*", action, payload=payload)

    def get_json(self):
        if len(self.request.body) == 0:
            return {}
        try:
            json = tornado.escape.json_decode(self.request.body)
            if not isinstance(json, dict):
                raise Exception("Please ensure posted data is of type application/json")
            return json
        except JSONDecodeError:
            raise Exception(
                f"JSON decode of request body failed on {self.request.uri}."
                " Please ensure all requests are of type application/json."
            )

    def error(self, message, data={}, status=400, extra={}):
        """Push an error message to the frontend via WebSocket connection.

        The return JSON has the following format::

          {
            "status": "error",
            "data": ...,
            ...extra...
          }

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
        extra : dict
            Extra fields to be included in the response.
        """
        self.set_header("Content-Type", "application/json")
        self.set_status(status)
        self.write({"status": "error", "message": message, "data": data, **extra})

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

    def success(self, data={}, action=None, payload={}, status=200, extra={}):
        """Write data and send actions on API success.

        The return JSON has the following format::

          {
            "status": "success",
            "data": ...,
            ...extra...
          }

        Parameters
        ----------
        data : dict, optional
            The JSON returned by the API call in the `data` field.
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
        extra : dict
            Extra fields to be included in the response.
        """
        if action is not None:
            self.action(action, payload)

        self.set_header("Content-Type", "application/json")
        self.set_status(status)
        self.write(to_json({"status": "success", "data": data, **extra}))

    def write_error(self, status_code, exc_info=None):
        if exc_info is not None:
            err_cls, err, traceback = exc_info
            if isinstance(err_cls, AccessError):
                status_code = 401
        else:
            err = "An unknown error occurred"

        self.error(str(err), status=status_code)

    async def _get_client(self, timeout=5):
        IP = "127.0.0.1"
        PORT_SCHEDULER = self.cfg["ports.dask"]

        from distributed import Client

        client = await Client(
            f"{IP}:{PORT_SCHEDULER}", asynchronous=True, timeout=timeout
        )

        return client

    def push_notification(self, note, notification_type="info"):
        self.push(
            action="baselayer/SHOW_NOTIFICATION",
            payload={"note": note, "type": notification_type},
        )

    def get_query_argument(self, value, default=NoValue, **kwargs):
        if default != NoValue:
            kwargs["default"] = default
        arg = super().get_query_argument(value, **kwargs)
        if type(kwargs.get("default", None)) == bool:
            arg = str(arg).lower() in ["true", "yes", "t", "1"]
        return arg
