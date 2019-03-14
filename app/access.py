import functools
import tornado.web
from baselayer.app.custom_exceptions import AccessError
from baselayer.app.models import Role, User, Token


def auth_or_token(method):
    """Ensure that a user is signed in.

    This is a decorator for Tornado handler `get`, `put`, etc. methods.

    Signing in happens via the login page, or by using an auth token.
    To use an auth token, the `Authorization` header has to be
    provided, and has to be of the form `token 123efghj`.  E.g.:

      $ curl -v -H "Authorization: token 123efghj" http://localhost:5000/api/endpoint

    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        token_header = self.request.headers.get('Authorization', None)
        if token_header and token_header.startswith('token '):
            token_id = token_header.replace('token', '').strip()
            token = Token.query.get(token_id)
            if token is not None:
                self.current_user = token
            else:
                raise tornado.web.HTTPError(403)
            return method(self, *args, **kwargs)
        else:
            return tornado.web.authenticated(method)(self, *args, **kwargs)
    return wrapper


def permissions(acl_list):
    """Decorate methods with this to require that the current user have all the
    specified ACLs.
    """
    def check_acls(method):
        @auth_or_token
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            if not set(acl_list).issubset(self.current_user.permissions):
                raise tornado.web.HTTPError(403)
            return method(self, *args, **kwargs)
        return wrapper
    return check_acls
