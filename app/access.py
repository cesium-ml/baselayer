import functools
import tornado.web
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
