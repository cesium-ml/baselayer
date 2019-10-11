"""
Python Social Auth: storage and user model definitions

https://github.com/python-social-auth
"""

from social_tornado.models import init_social
from social_core.backends.google import GoogleOAuth2

from .models import Base, DBSession
from .env import load_env


class FakeGoogleOAuth2(GoogleOAuth2):
    @property
    def AUTHORIZATION_URL(self):
        return self.strategy.absolute_uri('/fakeoauth2/auth')

    @property
    def ACCESS_TOKEN_URL(self):
        # The web app connects to the OAuth provider using this URI.
        # The remote service verifies information provided to the user
        # when they connected to AUTHORIZATION_URL.
        #
        # - Why is this not set to an absolute URI, as done above for
        #   AUTHORIZATION_URI?
        #
        #   This call is made from the webserver itself, sometimes
        #   running inside a Docker container.  A server may be
        #   visible to the outside world on port 9000 (due to Docker
        #   port mapping), but from the perspective of (inside) the
        #   running container, the fakeoauth server only responds to
        #   `localhost:5000`.  If we try to connect to
        #   `localhost:9000/fakeoauth2`, we won't get through.
        #
        # Instead, we always connect to localhost:63000.

        env, cfg = load_env()
        return f'http://localhost:{cfg["ports.fake_oauth"]}/fakeoauth2/token'

    def user_data(self, access_token, *args, **kwargs):
        return {
            'id': 'testuser@cesium-ml.org',
            'email': 'testuser@cesium-ml.org'
        }


# Set up TornadoStorage
init_social(Base, DBSession,
            {'SOCIAL_AUTH_USER_MODEL': 'baselayer.app.models.User'})
