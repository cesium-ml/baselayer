import tornado.web

# This provides `login`, `complete`, and `disconnect` endpoints
from social_tornado.routes import SOCIAL_AUTH_ROUTES

from .handlers import (
    MainPageHandler,
    SocketAuthTokenHandler,
    ProfileHandler,
    LogoutHandler
)

from .env import load_env
env, cfg = load_env()


# Tornado settings
settings = {
    'template_path': './static',
    'login_url': '/',

    # Python Social Auth configuration
    'SOCIAL_AUTH_USER_MODEL': 'baselayer.app.models.User',
    'SOCIAL_AUTH_STORAGE': 'social_tornado.models.TornadoStorage',
    'SOCIAL_AUTH_STRATEGY': 'social_tornado.strategy.TornadoStrategy',
    'SOCIAL_AUTH_AUTHENTICATION_BACKENDS': (
        'social_core.backends.google.GoogleOAuth2',
    ),
    'SOCIAL_AUTH_LOGIN_URL': '/',
    'SOCIAL_AUTH_LOGIN_REDIRECT_URL': '/',  # on success
    'SOCIAL_AUTH_LOGIN_ERROR_URL': '/login-error/',

    'SOCIAL_AUTH_USER_FIELDS': ['username'],
    'SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL': True,
    'SOCIAL_AUTH_SESSION_EXPIRATION': True,

    'SOCIAL_AUTH_GOOGLE_OAUTH2_KEY':
        cfg['server.auth.google_oauth2_key'],
    'SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET': \
        cfg['server.auth.google_oauth2_secret'],
}

if cfg['server.auth.debug_login']:
    settings['SOCIAL_AUTH_AUTHENTICATION_BACKENDS'] = (
        'baselayer.app.psa.FakeGoogleOAuth2',
    )

handlers = SOCIAL_AUTH_ROUTES + [
    (r'/baselayer/socket_auth_token', SocketAuthTokenHandler),
    (r'/baselayer/profile', ProfileHandler),
    (r'/baselayer/logout', LogoutHandler),

    (r'/()', MainPageHandler),
    (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': 'static/'}),
    (r'/(favicon.png)', tornado.web.StaticFileHandler, {'path': 'static/'})
]
