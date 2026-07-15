import functools
import inspect

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


def auth_or_token(method):
    """Ensure that a user is signed in.

    This is a decorator for Tornado handler `get`, `put`, etc. methods.

    Signing in happens via the login page, or by using an auth token.
    To use an auth token, the `Authorization` header has to be
    provided, and has to be of the form `token 123efghj`.  E.g.:

      $ curl -v -H "Authorization: token 123efghj" http://localhost:5000/api/endpoint

    If `method` is a coroutine function, the token lookup runs against the
    async DB engine; otherwise the original sync path is used. The cookie
    auth path delegates to `tornado.web.authenticated` in both cases.
    """

    if inspect.iscoroutinefunction(method):

        @functools.wraps(method)
        async def async_wrapper(self, *args, **kwargs):
            token_header = self.request.headers.get("Authorization", None)
            if token_header is not None and token_header.startswith("token "):
                token_id = token_header.replace("token", "").strip()
                # Use the import via models module so monkeypatching/late
                # init by init_db() is reflected here.
                from baselayer.app import models as _models

                try:
                    async with _models.async_plain_session_factory() as session:
                        result = await session.scalars(_token_select_stmt(token_id))
                        token = result.first()
                except sa.exc.SQLAlchemyError as e:
                    # Don't leak the raw SQL/token id as a 500; return a retryable 503.
                    log(f"Token auth DB lookup failed for [{self.request.path}]: {e}")
                    raise tornado.web.HTTPError(503, DB_UNAVAILABLE_MSG) from None
                if token is not None:
                    self.current_user = token
                    if not token.created_by.is_active():
                        raise tornado.web.HTTPError(403, "User account expired")
                else:
                    raise tornado.web.HTTPError(401)
                return await method(self, *args, **kwargs)
            else:
                if self.current_user is not None:
                    if not self.current_user.is_active():
                        raise tornado.web.HTTPError(403, "User account expired")
                else:
                    raise tornado.web.HTTPError(
                        401,
                        'Credentials malformed; expected form "Authorization: token abc123"',
                    )
                # tornado.web.authenticated returns whatever the method
                # returns; for an async method that's a coroutine to await.
                result = tornado.web.authenticated(method)(self, *args, **kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result

        async_wrapper.__authenticated__ = True
        return async_wrapper

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        token_header = self.request.headers.get("Authorization", None)
        if token_header is not None and token_header.startswith("token "):
            token_id = token_header.replace("token", "").strip()
            try:
                with DBSession() as session:
                    token = session.scalars(_token_select_stmt(token_id)).first()
            except sa.exc.SQLAlchemyError as e:
                # Don't leak the raw SQL/token id as a 500; return a retryable 503.
                log(f"Token auth DB lookup failed for [{self.request.path}]: {e}")
                raise tornado.web.HTTPError(503, DB_UNAVAILABLE_MSG) from None
            if token is not None:
                self.current_user = token
                if not token.created_by.is_active():
                    raise tornado.web.HTTPError(403, "User account expired")
            else:
                raise tornado.web.HTTPError(401)
            return method(self, *args, **kwargs)
        else:
            if self.current_user is not None:
                if not self.current_user.is_active():
                    raise tornado.web.HTTPError(403, "User account expired")
            else:
                raise tornado.web.HTTPError(
                    401,
                    'Credentials malformed; expected form "Authorization: token abc123"',
                )
            return tornado.web.authenticated(method)(self, *args, **kwargs)

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
                if not (
                    set(acl_list).issubset(self.current_user.permissions)
                    or "System admin" in self.current_user.permissions
                ):
                    raise tornado.web.HTTPError(401)
                return await method(self, *args, **kwargs)

            async_wrapper.__permissions__ = acl_list
            return async_wrapper

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
