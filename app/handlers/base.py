import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from json.decoder import JSONDecodeError

import sqlalchemy
import tornado.escape
from tornado.log import app_log
from tornado.web import HTTPError, RequestHandler

from ...log import make_log
from .. import psa
from ..access import db_error_503
from ..env import load_env
from ..flow import Flow
from ..json_util import to_json
from ..models import (
    AsyncVerifiedSession,
    DBSession,
    User,
    VerifiedSession,
    bulk_verify,
    db_engine,
    pending_rows,
    session_context_id,
)

env, cfg = load_env()
log = make_log("basehandler")

# The PSA onboarding pipeline raises a bare Exception, so there is no status to test.
EXPECTED_EXCEPTIONS = [
    "Authentication Error:",
    "User account expired",
    "Credentials malformed",
    "Method Not Allowed",
    "Unauthorized",
    "read-only access",
]


class NoValue:
    pass


class PSABaseHandler(RequestHandler):
    """
    Mixin used by Python Social Auth
    """

    # Read by `access.auth_or_token`; the token path never calls get_current_user.
    is_anonymous_user = False

    def user_id(self):
        return self.get_secure_cookie("user_id")

    def get_current_user(self):
        # Tornado calls this once per request and caches it as `self.current_user`.
        user = self._signed_in_user()
        if user is not None:
            return user

        cfg = self.application.cfg
        if not cfg.get("app.anonymous_access", False):
            return None
        username = cfg.get("app.anonymous_user") or "anonymous"
        with db_error_503(self.request.path), DBSession() as session:
            user = session.scalars(
                sqlalchemy.select(User).where(User.username == username)
            ).first()
        self.is_anonymous_user = user is not None
        return user

    def _signed_in_user(self):
        user_id = self.user_id()
        oauth_uid = self.get_secure_cookie("user_oauth_uid")
        if not user_id or not oauth_uid:
            return None
        user_id = int(user_id)

        with db_error_503(self.request.path), DBSession() as session:
            try:
                user = session.scalars(
                    sqlalchemy.select(User).where(User.id == user_id)
                ).first()
                if user is None:
                    return None
                sa = session.scalars(
                    sqlalchemy.select(psa.TornadoStorage.user).where(
                        psa.TornadoStorage.user.user_id == user.id
                    )
                ).first()
                # No SocialAuth entry; probably machine generated user
                if sa is None or sa.uid.encode("utf-8") == oauth_uid:
                    return user
                return None
            except sqlalchemy.exc.SQLAlchemyError:
                # Let db_error_503 answer, not a misleading 401.
                raise
            except Exception as e:
                session.rollback()
                log(f"Could not get current user: {e}")
                return None

    def login_user(self, user):
        with db_error_503(self.request.path), DBSession() as session:
            try:
                self.set_secure_cookie("user_id", str(user.id))
                user = session.scalars(
                    sqlalchemy.select(User).where(User.id == user.id)
                ).first()
                if user is None:
                    return
                sa = session.scalars(
                    sqlalchemy.select(psa.TornadoStorage.user).where(
                        psa.TornadoStorage.user.user_id == user.id
                    )
                ).first()
                if sa is not None:
                    self.set_secure_cookie("user_oauth_uid", sa.uid)
            except sqlalchemy.exc.SQLAlchemyError:
                # Let db_error_503 answer, not a silent failed login.
                raise
            except Exception as e:
                session.rollback()
                log(f"Could not login user: {e}")

    def write_error(self, status_code, exc_info=None):
        err = exc_info[1] if exc_info is not None else "An unknown error occurred"
        self.render("loginerror.html", app=cfg["app"], error_message=str(err))

    def log_exception(self, typ=None, value=None, tb=None):
        v_str = str(value)
        # 4xx is the client's fault; only 5xx and uncaught exceptions are ours.
        is_client_error = (
            isinstance(value, HTTPError) and 400 <= value.status_code < 500
        )
        if is_client_error or any(
            exception in v_str for exception in EXPECTED_EXCEPTIONS
        ):
            log(f"Error response returned by [{self.request.path}]: [{v_str}]")
        else:
            app_log.error(
                "Uncaught exception %s\n%r",
                self._request_summary(),
                self.request,
                exc_info=(typ, value, tb),
            )

    def on_finish(self):
        try:
            DBSession.remove()
        except Exception as e:
            # remove() rolls back, which fails if pgbouncer already closed the connection.
            log(f"Session cleanup failed, discarding it: {e}")
            try:
                DBSession.registry.clear()
            except Exception:
                pass


class BaseHandler(PSABaseHandler):
    @contextmanager
    def Session(self):
        """A session scoped to the request, that verifies on commit that every
        row being written is accessible to the handler's `current_user`.
        """
        with VerifiedSession(self.current_user) as session:
            # re-attach current_user, the commit-time check uses it as the accessor
            session.add(self.current_user)
            yield session

    @asynccontextmanager
    async def AsyncSession(self):
        """Async counterpart of `Session()`. Yields an `_AsyncVerifiedSession`
        bound to the async engine, with the handler's current user merged so
        that the commit-time access-control check has the right accessor.

        Usage:
            async with self.AsyncSession() as session:
                result = await session.scalars(MyModel.select(session.user_or_token))
                ...
                await session.commit()
        """
        async with AsyncVerifiedSession(self.current_user) as session:
            # load=False: the user comes from the auth lookup's session, so merging issues no SQL.
            session.user_or_token = await session.merge(self.current_user, load=False)
            yield session

    def verify_permissions(self):
        """Check that the current user has permission to create, read,
        update, or delete rows that are present in the session. If not,
        raise an AccessError (causing the transaction to fail and the API to
        respond with 401).
        """
        read_rows, updated_rows, deleted_rows, new_rows = pending_rows(DBSession())

        # deleted rows are gone from the transaction once flushed, so check them first
        for mode, collection in zip(
            ["read", "update", "delete"],
            [read_rows, updated_rows, deleted_rows],
        ):
            bulk_verify(mode, collection, self.current_user)

        # flush so that new rows can be joined against while checking them
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

        if self.path_args:
            self.path_args = [
                arg.lstrip("/") or None if arg is not None else None
                for arg in self.path_args
            ]

        # make "no argument" explicit, so get/post/put/delete need no optional kwarg
        if len(self.path_args) == 1 and self.path_args[0] is None:
            self.path_args = []

        for i in range(5):
            if db_engine() is not None:
                break
            if i == 4:
                raise RuntimeError("Could not connect to the database")
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
        err = exc_info[1] if exc_info is not None else "An unknown error occurred"
        self.error(str(err), status=status_code)

    def push_notification(self, note, notification_type="info"):
        self.push(
            action="baselayer/SHOW_NOTIFICATION",
            payload={"note": note, "type": notification_type},
        )

    def get_query_argument(self, value, default=NoValue, type=None, **kwargs):
        """Get a query-string argument with optional type coercion.

        Parameters
        ----------
        value : str
            Name of the query parameter.
        default : any, optional
            Value to return when the parameter is absent.
        type : callable, optional
            If provided (e.g. ``float`` / ``int``), the returned string is
            passed through this callable. Required for parameters that go
            into SQL comparisons against non-text columns — psycopg v3
            binds Python strings as VARCHAR, so the database refuses to
            compare e.g. ``double precision`` to ``character varying``.
            If the value can't be coerced, ``default`` is returned.
        """
        if default != NoValue:
            kwargs["default"] = default
        arg = super().get_query_argument(value, **kwargs)
        default_val = kwargs.get("default", None)
        if isinstance(default_val, bool):
            arg = str(arg).lower() in ["true", "yes", "t", "1"]
        elif type is not None and arg is not None and arg is not default_val:
            try:
                arg = type(arg)
            except (TypeError, ValueError):
                arg = default_val
        return arg
