"""
Python Social Auth: storage and user model definitions

https://github.com/python-social-auth
"""

from social_tornado.models import init_social
from social_core.backends.google import GoogleOAuth2

from .models import Base, DBSession


class FakeGoogleOAuth2(GoogleOAuth2):
    @property
    def AUTHORIZATION_URL(self):
        return self.strategy.absolute_uri('/fakeoauth2/auth')

    @property
    def ACCESS_TOKEN_URL(self):
        return self.strategy.absolute_uri('/fakeoauth2/token')

    def user_data(self, access_token, *args, **kwargs):
        return {
            'id': 'testuser@cesium-ml.org',
            'emails': [{'value': 'testuser@cesium-ml.org', 'type': 'home'}]
        }


# Set up TornadoStorage
init_social(Base, DBSession,
            {'SOCIAL_AUTH_USER_MODEL': 'baselayer.app.models.User'})
