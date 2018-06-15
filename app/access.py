import functools
import tornado.web
from baselayer.app.custom_exceptions import AccessError
from baselayer.app.models import Role, User, Token


def auth_or_token(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        data = self.get_json()
        if 'token' in data:
            token = Token.query.get(data['token'])
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
