"""
Python Social Auth: storage and user model definitions

https://github.com/python-social-auth
"""

from social_tornado.models import init_social
from social_core.backends.google import GoogleOAuth2

from .env import load_env
from .models import Base, DBSession


class FakeGoogleOAuth2(GoogleOAuth2):
    env, cfg = load_env()
    base_url = cfg['server:url'].rstrip(':0123456789')  # strip :<port>
    print('base_url:', base_url)
    AUTHORIZATION_URL = f'{base_url}:63000/fakeoauth2/auth'
    ACCESS_TOKEN_URL = f'{base_url}:63000/fakeoauth2/token'

    def user_data(self, access_token, *args, **kwargs):
        return {
            'id': 'testuser@cesium-ml.org',
            'emails': [{'value': 'testuser@cesium-ml.org', 'type': 'home'}]
        }


# Set up TornadoStorage
init_social(Base, DBSession,
            {'SOCIAL_AUTH_USER_MODEL': 'baselayer.app.models.User'})
