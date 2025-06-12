from functools import wraps

from baselayer.app.handlers.base import BaseHandler
from social_core.actions import do_auth, do_complete, do_disconnect
from social_core.backends.utils import get_backend
from social_core.utils import get_strategy, setting_name

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
            self.backend = load_backend(self, self.strategy, backend, uri)
            return func(self, backend, *args, **kwargs)

        return wrapper

    return decorator


class AuthHandler(BaseHandler):
    def get(self, backend):
        self._auth(backend)

    def post(self, backend):
        self._auth(backend)

    @psa("complete")
    def _auth(self, backend):
        do_auth(self.backend)


class CompleteHandler(BaseHandler):
    def get(self, backend):
        self._complete(backend)

    def post(self, backend):
        self._complete(backend)

    @psa("complete")
    def _complete(self, backend):
        do_complete(
            self.backend,
            login=lambda backend, user, social_user: self.login_user(user),
            user=self.get_current_user(),
        )


class DisconnectHandler(BaseHandler):
    def post(self):
        do_disconnect()
