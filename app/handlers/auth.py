from functools import wraps

import tornado.web
from social_core.actions import do_auth, do_complete, do_disconnect
from social_core.backends.utils import get_backend
from social_core.exceptions import AuthException, MissingBackend
from social_core.utils import get_strategy, setting_name

from baselayer.app.handlers.base import BaseHandler
from baselayer.log import make_log

log = make_log("auth")

DEFAULTS = {
    "STORAGE": "baselayer.app.psa.TornadoStorage",
    "STRATEGY": "baselayer.app.psa.TornadoStrategy",
}


def get_helper(request_handler, name):
    return request_handler.settings.get(setting_name(name), DEFAULTS.get(name, None))


def load_strategy(request_handler):
    strategy = get_helper(request_handler, "STRATEGY")
    storage = get_helper(request_handler, "STORAGE")
    return get_strategy(strategy, storage, request_handler)


def load_backend(request_handler, strategy, name, redirect_uri):
    backends = get_helper(request_handler, "AUTHENTICATION_BACKENDS")
    Backend = get_backend(backends, name)
    return Backend(strategy, redirect_uri)


def psa(redirect_uri=None):
    def decorator(func):
        @wraps(func)
        def wrapper(self, backend, *args, **kwargs):
            uri = redirect_uri
            if uri and not uri.startswith("/"):
                uri = self.reverse_url(uri, backend)
            self.strategy = load_strategy(self)
            try:
                self.backend = load_backend(self, self.strategy, backend, uri)
            except MissingBackend:
                raise tornado.web.HTTPError(
                    400, f"Unknown authentication backend: {backend}"
                )
            return func(self, backend, *args, **kwargs)

        return wrapper

    return decorator


def _failed(handler, backend, exc):
    # Almost always user-side (spent code, dismissed consent), not a server fault.
    log(f"Authentication with {backend} failed: {exc}")
    handler.redirect(handler.settings.get("SOCIAL_AUTH_LOGIN_ERROR_URL", "/"))


class AuthHandler(BaseHandler):
    def get(self, backend):
        self._auth(backend)

    def post(self, backend):
        self._auth(backend)

    @psa("complete")
    def _auth(self, backend):
        try:
            do_auth(self.backend)
        except AuthException as e:
            _failed(self, backend, e)


class CompleteHandler(BaseHandler):
    def get(self, backend):
        self._complete(backend)

    def post(self, backend):
        self._complete(backend)

    @psa("complete")
    def _complete(self, backend):
        try:
            do_complete(
                self.backend,
                login=lambda backend, user, social_user: self.login_user(user),
                user=self._signed_in_user(),
            )
        except AuthException as e:
            _failed(self, backend, e)


class DisconnectHandler(BaseHandler):
    def post(self):
        do_disconnect()
