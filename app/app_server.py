import tornado.web

from .auth_backends import configured_backends, setting_prefix
from .env import load_env
from .handlers import (
    AuthHandler,
    CompleteHandler,
    DisconnectHandler,
    LogoutHandler,
    MainPageHandler,
    ProfileHandler,
    SocketAuthTokenHandler,
)

env, cfg = load_env()


# Tornado settings
settings = {
    "template_path": "./static",
    "login_url": "/",
    # Python Social Auth configuration
    "SOCIAL_AUTH_USER_MODEL": "baselayer.app.models.User",
    "SOCIAL_AUTH_STORAGE": "baselayer.app.psa.TornadoStorage",
    "SOCIAL_AUTH_STRATEGY": "baselayer.app.psa.TornadoStrategy",
    "SOCIAL_AUTH_LOGIN_URL": "/",
    "SOCIAL_AUTH_LOGIN_REDIRECT_URL": "/",  # on success
    "SOCIAL_AUTH_LOGIN_ERROR_URL": "/",
    "SOCIAL_AUTH_USER_FIELDS": ["username"],
    "SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL": cfg.get(
        "server.auth.username_is_email", True
    ),
    "SOCIAL_AUTH_SESSION_EXPIRATION": True,
    "SOCIAL_AUTH_REDIRECT_IS_HTTPS": cfg["server.ssl"],
    "SOCIAL_AUTH_URLOPEN_TIMEOUT": cfg["server.auth.google_oauth2_timeout"],
}

auth_backends = configured_backends()
settings["SOCIAL_AUTH_AUTHENTICATION_BACKENDS"] = tuple(
    backend["class"] for backend in auth_backends
)
for backend in auth_backends:
    prefix = setting_prefix(backend["name"])
    settings[f"SOCIAL_AUTH_{prefix}_KEY"] = backend["key"]
    settings[f"SOCIAL_AUTH_{prefix}_SECRET"] = backend["secret"]
    settings[f"SOCIAL_AUTH_{prefix}_USE_UNIQUE_USER_ID"] = backend["use_unique_user_id"]
    for key, value in backend["settings"].items():
        settings[f"SOCIAL_AUTH_{prefix}_{key.upper()}"] = value

if cfg["server.auth.debug_login"]:
    # The fake provider impersonates the first configured backend, so
    # /login/<backend> stays the same in test mode.
    settings["SOCIAL_AUTH_AUTHENTICATION_BACKENDS"] = ("baselayer.app.psa.FakeOAuth2",)

SOCIAL_AUTH_ROUTES = [
    tornado.web.url(r"/login/(?P<backend>[^/]+)/?", AuthHandler, name="begin"),
    tornado.web.url(r"/complete/(?P<backend>[^/]+)/", CompleteHandler, name="complete"),
    tornado.web.url(
        r"/disconnect/(?P<backend>[^/]+)/?", DisconnectHandler, name="disconnect"
    ),
    tornado.web.url(
        r"/disconnect/(?P<backend>[^/]+)/(?P<association_id>\d+)/?",
        DisconnectHandler,
        name="disconnect_individual",
    ),
]

handlers = SOCIAL_AUTH_ROUTES + [
    (r"/baselayer/socket_auth_token", SocketAuthTokenHandler),
    (r"/baselayer/profile", ProfileHandler),
    (r"/baselayer/logout", LogoutHandler),
    (r"/()", MainPageHandler),
    (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static/"}),
    (r"/(favicon.png)", tornado.web.StaticFileHandler, {"path": "static/"}),
]
