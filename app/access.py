import time
from collections import defaultdict
import functools
import tornado.web
from baselayer.app.custom_exceptions import AccessError
from baselayer.app.models import Role, User, Token
from baselayer.app.env import load_env


_, cfg = load_env()
token_request_times = defaultdict(list)


def rate_limit_exceeded(token_id):
    """Return boolean indicating whether rate limit has been exceeded by specified token, while updating per-token requests tracking cache."""
    token_request_times[token_id] = [
        t
        for t in token_request_times[token_id]
        if (time.time() - t)
        < float(cfg["misc"]["rate_limit_100_requests_per_n_seconds"])
    ]
    if len(token_request_times[token_id]) >= 100:
        return True
    token_request_times[token_id].append(time.time())
    return False


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
        token_header = self.request.headers.get("Authorization", None)
        if token_header and token_header.startswith("token "):
            token_id = token_header.replace("token", "").strip()
            token = Token.query.get(token_id)
            if token is not None:
                self.current_user = token
                if not token.created_by.is_active():
                    raise tornado.web.HTTPError(403, "User account expired")
                if not token.is_admin:
                    if rate_limit_exceeded(token.id):
                        raise tornado.web.HTTPError(
                            503,
                            "API rate limit exceeded; please throttle your requests",
                        )
            else:
                raise tornado.web.HTTPError(401)
            return method(self, *args, **kwargs)
        else:
            if not self.current_user.is_active():
                raise tornado.web.HTTPError(403, "User account expired")
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
            if not (
                set(acl_list).issubset(self.current_user.permissions)
                or "System admin" in self.current_user.permissions
            ):
                raise tornado.web.HTTPError(401)
            return method(self, *args, **kwargs)

        return wrapper

    return check_acls
