import functools
import tornado.web
import jwt
from baselayer.app.custom_exceptions import AccessError
from baselayer.app.models import Role, User


def permissions(acl_list):
    """Decorate methods with this to require that the current user have all the
    given ACLs.
    """
    def check_acls(method):
        @tornado.web.authenticated
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            if not set(acl_list).issubset(self.current_user.permissions):
                raise tornado.web.HTTPError(403)
            return method(self, *args, **kwargs)
        return wrapper
    return check_acls


def auth_or_token(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        cookies_dict = {k: morsel.value for k, morsel in self.request.cookies.items()}
        if 'token' in cookies_dict:
            try:
                raw_token = jwt.decode(cookies_dict['token'],
                                       self.cfg['app:secret-key'])['token']
            except (jwt.exceptions.DecodeError, KeyError):
                raise AccessError('Invalid auth token in request cookies')
            matching_users = list(User.query.filter(User.username == raw_token))
            if len(matching_users) == 1:
                self.current_user = matching_users[0]
            else:
                raise tornado.web.HTTPError(403)
            return method(self, *args, **kwargs)
        else:
            return tornado.web.authenticated(method)(self, *args, **kwargs)
    return wrapper
