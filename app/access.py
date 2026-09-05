import functools
import inspect
from contextlib import contextmanager

import sqlalchemy as sa
import tornado.web
from sqlalchemy.orm import joinedload

from baselayer.app.custom_exceptions import AccessError  # noqa: F401
from baselayer.app.models import (  # noqa: F401
    DBSession,
    Role,
    Token,
    User,
)
from baselayer.log import make_log

log = make_log("access")

DB_UNAVAILABLE_MSG = "Database is temporarily unavailable; please retry shortly."


@contextmanager
def db_error_503(path):
    """Turn an auth-boundary DB failure into a retryable 503 (no SQL leak)."""
    try:
        yield
    except sa.exc.SQLAlchemyError as e:
        log(f"Auth DB access failed for [{path}]: {e}")
        raise tornado.web.HTTPError(503, DB_UNAVAILABLE_MSG) from None


#: HTTP methods that do not modify state, and so are available to anonymous users.
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _token_select_stmt(token_id):
    return (
        sa.select(Token)
        .options(
            joinedload(Token.created_by).options(
                joinedload(User.acls),
                joinedload(User.roles),
            )
        )
        .where(Token.id == token_id)
    )


def _token_id_from_header(handler):
    """Return the token id in the `Authorization` header, or None if the
    request does not present one."""
    header = handler.request.headers.get("Authorization") or ""
    if not header.startswith("token "):
        return None
    return header.removeprefix("token").strip()


def _authorize_token(handler, token):
    """Install a looked-up token as the request's credentials."""
    if token is None:
        raise tornado.web.HTTPError(401)
    if not token.created_by.is_active():
        raise tornado.web.HTTPError(403, "User account expired")
    handler.current_user = token


def _authorize_current_user(handler):
    """Validate the cookie-authenticated user already on the request."""
    if handler.current_user is None:
        raise tornado.web.HTTPError(
            401,
            'Credentials malformed; expected form "Authorization: token abc123"',
        )
    if not handler.current_user.is_active():
        raise tornado.web.HTTPError(403, "User account expired")
    # The anonymous fallback account is served whenever no valid user is signed
    # in; restrict it to safe (read-only) methods. Keying off is_anonymous_user
    # (not a present user_id cookie) also covers cookies that are present but
    # invalid.
    if handler.is_anonymous_user and handler.request.method not in SAFE_METHODS:
        raise tornado.web.HTTPError(403, "Anonymous users have read-only access")


def _authorize_acls(handler, acl_list):
    """Require that the request's credentials carry all of `acl_list`."""
    permissions = handler.current_user.permissions
    if not (set(acl_list).issubset(permissions) or "System admin" in permissions):
        raise tornado.web.HTTPError(401)


def auth_or_token(method):
    """Ensure that a user is signed in.

    This is a decorator for Tornado handler `get`, `put`, etc. methods.

    Signing in happens via the login page, or by using an auth token.
    To use an auth token, the `Authorization` header has to be
    provided, and has to be of the form `token 123efghj`.  E.g.:

      $ curl -v -H "Authorization: token 123efghj" http://localhost:5000/api/endpoint

    If `method` is a coroutine function, the token lookup runs against the
    async DB engine; otherwise the original sync path is used. That lookup is
    the only step that differs between the two; every authorization decision
    is shared.
    """

    if inspect.iscoroutinefunction(method):

        @functools.wraps(method)
        async def async_wrapper(self, *args, **kwargs):
            token_id = _token_id_from_header(self)
            if token_id is not None:
                # Use the import via models module so monkeypatching/late
                # init by init_db() is reflected here.
                from baselayer.app import models as _models

                with db_error_503(self.request.path):
                    async with _models.async_plain_session_factory() as session:
                        result = await session.scalars(_token_select_stmt(token_id))
                        token = result.first()
                _authorize_token(self, token)
                return await method(self, *args, **kwargs)

            _authorize_current_user(self)
            return await method(self, *args, **kwargs)

        async_wrapper.__authenticated__ = True
        return async_wrapper

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        token_id = _token_id_from_header(self)
        if token_id is not None:
            with db_error_503(self.request.path):
                with DBSession() as session:
                    token = session.scalars(_token_select_stmt(token_id)).first()
            _authorize_token(self, token)
            return method(self, *args, **kwargs)

        _authorize_current_user(self)
        return method(self, *args, **kwargs)

    wrapper.__authenticated__ = True
    return wrapper


def permissions(acl_list):
    """Decorate methods with this to require that the current user have all the
    specified ACLs.
    """

    def check_acls(method):
        if inspect.iscoroutinefunction(method):

            @auth_or_token
            @functools.wraps(method)
            async def async_wrapper(self, *args, **kwargs):
                _authorize_acls(self, acl_list)
                return await method(self, *args, **kwargs)

            async_wrapper.__permissions__ = acl_list
            return async_wrapper

        @auth_or_token
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            _authorize_acls(self, acl_list)
            return method(self, *args, **kwargs)

        wrapper.__permissions__ = acl_list
        return wrapper

    return check_acls
