import functools
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


async def load_token(token_id, path):
    """Load a Token (with its creator's ACLs and roles) via the async engine.

    Called from `BaseHandler.prepare()`: `get_current_user()` may not be a
    coroutine, so async credential resolution belongs in `prepare()`, per
    the Tornado docs.
    """
    # Use the import via models module so monkeypatching/late
    # init by init_db() is reflected here.
    from baselayer.app import models as _models

    with db_error_503(path):
        async with _models.async_plain_session_factory() as session:
            result = await session.scalars(_token_select_stmt(token_id))
            return result.first()


def auth_or_token(method):
    """Ensure that a user or token is signed in.

    This is a decorator for Tornado handler `get`, `put`, etc. methods.

    Signing in happens via the login page, or by using an auth token.
    To use an auth token, the `Authorization` header has to be
    provided, and has to be of the form `token 123efghj`.  E.g.:

      $ curl -v -H "Authorization: token 123efghj" http://localhost:5000/api/endpoint

    Credential resolution (token lookup, cookie check, anonymous fallback)
    happens in `BaseHandler.prepare()` / `get_current_user()`; this
    decorator only enforces that a valid, active user or token resulted.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        user_or_token = self.current_user
        if user_or_token is None:
            raise tornado.web.HTTPError(
                401,
                'Credentials malformed; expected form "Authorization: token abc123"',
            )
        if isinstance(user_or_token, Token):
            if not user_or_token.created_by.is_active():
                raise tornado.web.HTTPError(403, "User account expired")
            return method(self, *args, **kwargs)
        if not user_or_token.is_active():
            raise tornado.web.HTTPError(403, "User account expired")
        # The anonymous fallback account is served whenever no valid
        # user is signed in; restrict it to safe (read-only) methods.
        # Keying off is_anonymous_user (not a present user_id cookie)
        # also covers cookies that are present but invalid.
        if getattr(self, "is_anonymous_user", False) and (
            self.request.method not in ("GET", "HEAD", "OPTIONS")
        ):
            raise tornado.web.HTTPError(403, "Anonymous users have read-only access")
        # tornado.web.authenticated returns whatever the method returns;
        # for an async method Tornado awaits that result itself.
        return tornado.web.authenticated(method)(self, *args, **kwargs)

    wrapper.__authenticated__ = True
    return wrapper


def permissions(acl_list):
    """Decorate methods with this to require that the current user have all the
    specified ACLs.
    """

    def check_acls(method):
        @auth_or_token
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            if not (
                set(acl_list).issubset(self.current_user.permissions)
                or "System admin" in self.current_user.permissions
            ):
                raise tornado.web.HTTPError(401)
            return method(self, *args, **kwargs)

        wrapper.__permissions__ = acl_list
        return wrapper

    return check_acls
