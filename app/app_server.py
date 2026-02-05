import tornado.web

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
    "SOCIAL_AUTH_AUTHENTICATION_BACKENDS": (
        "social_core.backends.google.GoogleOAuth2",
    ),
    "SOCIAL_AUTH_LOGIN_URL": "/",
    "SOCIAL_AUTH_LOGIN_REDIRECT_URL": "/",  # on success
    "SOCIAL_AUTH_LOGIN_ERROR_URL": "/login-error/",
    "SOCIAL_AUTH_USER_FIELDS": ["username"],
    "SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL": cfg.get(
        "server.auth.username_is_full_email", True
    ),
    "SOCIAL_AUTH_SESSION_EXPIRATION": True,
    "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY": cfg["server.auth.google_oauth2_key"],
    "SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET": cfg["server.auth.google_oauth2_secret"],
    "SOCIAL_AUTH_REDIRECT_IS_HTTPS": cfg["server.ssl"],
    "SOCIAL_AUTH_URLOPEN_TIMEOUT": cfg["server.auth.google_oauth2_timeout"],
}

if cfg["server.auth.debug_login"]:
    settings["SOCIAL_AUTH_AUTHENTICATION_BACKENDS"] = (
        "baselayer.app.psa.FakeGoogleOAuth2",
    )

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
