import functools
import inspect
from contextlib import contextmanager

import sqlalchemy as sa
import tornado.web
from sqlalchemy.orm import joinedload

from baselayer.app import models
from baselayer.app.custom_exceptions import AccessError  # noqa: F401
from baselayer.app.models import DBSession, Token, User
from baselayer.log import make_log

log = make_log("access")

DB_UNAVAILABLE_MSG = "Database is temporarily unavailable; please retry shortly."
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


@contextmanager
def db_error_503(path):
    """Turn an auth-boundary DB failure into a retryable 503 (no SQL leak)."""
    try:
        yield
    except sa.exc.SQLAlchemyError as e:
        log(f"Auth DB access failed for [{path}]: {e}")
        raise tornado.web.HTTPError(503, DB_UNAVAILABLE_MSG) from None


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
    header = handler.request.headers.get("Authorization") or ""
    if not header.startswith("token "):
        return None
    return header.removeprefix("token").strip()


def _lookup_token(handler, token_id):
    with db_error_503(handler.request.path):
        with DBSession() as session:
            return session.scalars(_token_select_stmt(token_id)).first()


async def _lookup_token_async(handler, token_id):
    with db_error_503(handler.request.path):
        async with models.async_plain_session_factory() as session:
            result = await session.scalars(_token_select_stmt(token_id))
            return result.first()


def _authorize_token(handler, token):
    if token is None:
        raise tornado.web.HTTPError(401)
    if not token.created_by.is_active():
        raise tornado.web.HTTPError(403, "User account expired")
    handler.current_user = token


def _authorize_user(handler):
    # Reading current_user resolves the anonymous fallback and sets is_anonymous_user.
    user = handler.current_user
    if user is None:
        raise tornado.web.HTTPError(
            401,
            'Credentials malformed; expected form "Authorization: token abc123"',
        )
    if not user.is_active():
        raise tornado.web.HTTPError(403, "User account expired")
    if handler.is_anonymous_user and handler.request.method not in SAFE_METHODS:
        raise tornado.web.HTTPError(403, "Anonymous users have read-only access")


def _authorize_acls(handler, acl_list):
    granted = handler.current_user.permissions
    if not (set(acl_list).issubset(granted) or "System admin" in granted):
        raise tornado.web.HTTPError(401)


def auth_or_token(method):
    """Require a signed-in user, or an `Authorization: token <id>` header.

    Decorates a Tornado handler's `get`, `post`, ... method:

      $ curl -v -H "Authorization: token 123efghj" http://localhost:5000/api/endpoint
    """
    if inspect.iscoroutinefunction(method):

        @functools.wraps(method)
        async def wrapper(self, *args, **kwargs):
            token_id = _token_id_from_header(self)
            if token_id is None:
                _authorize_user(self)
            else:
                _authorize_token(self, await _lookup_token_async(self, token_id))
            return await method(self, *args, **kwargs)
    else:

        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            token_id = _token_id_from_header(self)
            if token_id is None:
                _authorize_user(self)
            else:
                _authorize_token(self, _lookup_token(self, token_id))
            return method(self, *args, **kwargs)

    wrapper.__authenticated__ = True
    return wrapper


def permissions(acl_list):
    """Require all of `acl_list`; the `System admin` ACL satisfies any list."""

    def check_acls(method):
        if inspect.iscoroutinefunction(method):

            @auth_or_token
            @functools.wraps(method)
            async def wrapper(self, *args, **kwargs):
                _authorize_acls(self, acl_list)
                return await method(self, *args, **kwargs)
        else:

            @auth_or_token
            @functools.wraps(method)
            def wrapper(self, *args, **kwargs):
                _authorize_acls(self, acl_list)
                return method(self, *args, **kwargs)

        wrapper.__permissions__ = acl_list
        return wrapper

    return check_acls
