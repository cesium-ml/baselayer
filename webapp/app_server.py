import tornado.web

import sys


from .handlers import SocketAuthTokenHandler


def make_app():
    """Create and return a `tornado.web.Application` object with specified
    handlers and settings.
    """
    settings = {
        'static_path': '../public',
        'autoreload': '--debug' in sys.argv
        }

    handlers = [
        (r'/socket_auth_token', SocketAuthTokenHandler),
        (r'/(.*)', tornado.web.StaticFileHandler,
         {'path': 'public/', 'default_filename': 'index.html'})
    ]

    return tornado.web.Application(handlers, **settings)
