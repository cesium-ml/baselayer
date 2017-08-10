"""
Python Social Auth: storage and user model definitions

https://github.com/python-social-auth
"""

from social_sqlalchemy.storage import (SQLAlchemyUserMixin,
                                       SQLAlchemyAssociationMixin,
                                       SQLAlchemyNonceMixin,
                                       SQLAlchemyCodeMixin,
                                       SQLAlchemyPartialMixin,
                                       BaseSQLAlchemyStorage)
from social_tornado.models import TornadoStorage, init_social
from social_core.backends.google import GoogleOAuth2

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from .models import Base, User, DBSession

class FakeGoogleOAuth2(GoogleOAuth2):
    AUTHORIZATION_URL = 'http://localhost:63000/fakeoauth2/auth'
    ACCESS_TOKEN_URL = 'http://localhost:63000/fakeoauth2/token'

    def user_data(self, access_token, *args, **kwargs):
        return {
            'id': 'testuser@cesium-ml.org',
            'emails': [{'value': 'testuser@cesium-ml.org', 'type': 'home'}]
        }


# Set up TornadoStorage
init_social(Base, DBSession,
            {'SOCIAL_AUTH_USER_MODEL': 'baselayer.app.models.User'})
