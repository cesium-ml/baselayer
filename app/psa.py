"""
Python Social Auth: storage and user model definitions

https://github.com/python-social-auth
"""

import base64
import json
import re
import time
import uuid
import warnings
from datetime import datetime, timedelta

from baselayer.app.models import Base, DBSession, User
from openid.association import Association as OpenIdAssociation
from social_core.backends.google import GoogleOAuth2
from social_core.exceptions import MissingBackend
from social_core.strategy import BaseStrategy, BaseTemplateStrategy
from social_core.utils import build_absolute_uri
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import backref, relationship
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.types import PickleType, Text
from tornado.template import Loader, Template

from .env import load_env

NO_ASCII_REGEX = re.compile(r"[^\x00-\x7F]+")
NO_SPECIAL_REGEX = re.compile(r"[^\w.@+_-]+", re.UNICODE)


class UserMixin:
    # Consider tokens that expire in 5 seconds as already expired
    ACCESS_TOKEN_EXPIRED_THRESHOLD = 5

    user = ""
    provider = ""
    uid = None
    extra_data = None

    def get_backend(self, strategy):
        return strategy.get_backend_class(self.provider)

    def get_backend_instance(self, strategy):
        try:
            return strategy.get_backend(self.provider)
        except MissingBackend:
            return None

    @property
    def access_token(self):
        """Return access_token stored in extra_data or None"""
        return self.extra_data.get("access_token")

    @property
    def tokens(self):
        warnings.warn("tokens is deprecated, use access_token instead")
        return self.access_token

    def refresh_token(self, strategy, *args, **kwargs):
        token = self.extra_data.get("refresh_token") or self.extra_data.get(
            "access_token"
        )
        backend = self.get_backend_instance(strategy)
        if token and backend and hasattr(backend, "refresh_token"):
            response = backend.refresh_token(token, *args, **kwargs)
            extra_data = backend.extra_data(self, self.uid, response, self.extra_data)
            if self.set_extra_data(extra_data):
                self.save()

    def expiration_timedelta(self):
        """Return provider session live seconds. Returns a timedelta ready to
        use with session.set_expiry().

        If provider returns a timestamp instead of session seconds to live, the
        timedelta is inferred from current time (using UTC timezone). None is
        returned if there's no value stored or it's invalid.
        """
        if self.extra_data and "expires" in self.extra_data:
            try:
                expires = int(self.extra_data.get("expires"))
            except (ValueError, TypeError):
                return None

            now = datetime.utcnow()

            # Detect if expires is a timestamp
            if expires > time.mktime(now.timetuple()):
                # expires is a datetime, return the remaining difference
                return datetime.utcfromtimestamp(expires) - now
            else:
                # expires is the time to live seconds since creation,
                # check against auth_time if present, otherwise return
                # the value
                auth_time = self.extra_data.get("auth_time")
                if auth_time:
                    reference = datetime.utcfromtimestamp(auth_time)
                    return (reference + timedelta(seconds=expires)) - now
                else:
                    return timedelta(seconds=expires)

    def expiration_datetime(self):
        # backward compatible alias
        return self.expiration_timedelta()

    def access_token_expired(self):
        """Return true / false if access token is already expired"""
        expiration = self.expiration_timedelta()
        return (
            expiration
            and expiration.total_seconds() <= self.ACCESS_TOKEN_EXPIRED_THRESHOLD
        )

    def get_access_token(self, strategy):
        """Returns a valid access token."""
        if self.access_token_expired():
            self.refresh_token(strategy)
        return self.access_token

    def set_extra_data(self, extra_data=None):
        if extra_data and self.extra_data != extra_data:
            if self.extra_data and not isinstance(self.extra_data, str):
                self.extra_data.update(extra_data)
            else:
                self.extra_data = extra_data
            return True

    @classmethod
    def clean_username(cls, value):
        """Clean username removing any unsupported character"""
        value = NO_ASCII_REGEX.sub("", value)
        value = NO_SPECIAL_REGEX.sub("", value)
        return value

    @classmethod
    def changed(cls, user):
        """The given user instance is ready to be saved"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get_username(cls, user):
        """Return the username for given user"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def user_model(cls):
        """Return the user model"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def username_max_length(cls):
        """Return the max length for username"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def allowed_to_disconnect(cls, user, backend_name, association_id=None):
        """Return if it's safe to disconnect the social account for the
        given user"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def disconnect(cls, entry):
        """Disconnect the social account for the given user"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def user_exists(cls, *args, **kwargs):
        """
        Return True/False if a User instance exists with the given arguments.
        Arguments are directly passed to filter() manager method.
        """
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def create_user(cls, *args, **kwargs):
        """Create a user instance"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get_user(cls, pk):
        """Return user instance for given id"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get_users_by_email(cls, email):
        """Return users instances for given email address"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get_social_auth(cls, provider, uid):
        """Return UserSocialAuth for given provider and uid"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get_social_auth_for_user(cls, user, provider=None, id=None):
        """Return all the UserSocialAuth instances for given user"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def create_social_auth(cls, user, uid, provider):
        """Create a UserSocialAuth instance for given user"""
        raise NotImplementedError("Implement in subclass")


class NonceMixin:
    """One use numbers"""

    server_url = ""
    timestamp = 0
    salt = ""

    @classmethod
    def use(cls, server_url, timestamp, salt):
        """Create a Nonce instance"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get(cls, server_url, salt):
        """Retrieve a Nonce instance"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def delete(cls, nonce):
        """Delete a Nonce instance"""
        raise NotImplementedError("Implement in subclass")


class AssociationMixin:
    """OpenId account association"""

    server_url = ""
    handle = ""
    secret = ""
    issued = 0
    lifetime = 0
    assoc_type = ""

    @classmethod
    def oids(cls, server_url, handle=None):
        kwargs = {"server_url": server_url}
        if handle is not None:
            kwargs["handle"] = handle
        return sorted(
            ((assoc.id, cls.openid_association(assoc)) for assoc in cls.get(**kwargs)),
            key=lambda x: x[1].issued,
            reverse=True,
        )

    @classmethod
    def openid_association(cls, assoc):
        secret = assoc.secret
        if not isinstance(secret, bytes):
            secret = secret.encode()
        return OpenIdAssociation(
            assoc.handle,
            base64.decodebytes(secret),
            assoc.issued,
            assoc.lifetime,
            assoc.assoc_type,
        )

    @classmethod
    def store(cls, server_url, association):
        """Create an Association instance"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def get(cls, *args, **kwargs):
        """Get an Association instance"""
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def remove(cls, ids_to_delete):
        """Remove an Association instance"""
        raise NotImplementedError("Implement in subclass")


class CodeMixin:
    email = ""
    code = ""
    verified = False

    def verify(self):
        self.verified = True
        self.save()

    @classmethod
    def generate_code(cls):
        return uuid.uuid4().hex

    @classmethod
    def make_code(cls, email):
        code = cls()
        code.email = email
        code.code = cls.generate_code()
        code.verified = False
        code.save()
        return code

    @classmethod
    def get_code(cls, code):
        raise NotImplementedError("Implement in subclass")


class PartialMixin:
    token = ""
    data = ""
    next_step = ""
    backend = ""

    @property
    def args(self):
        return self.data.get("args", [])

    @args.setter
    def args(self, value):
        self.data["args"] = value

    @property
    def kwargs(self):
        return self.data.get("kwargs", {})

    @kwargs.setter
    def kwargs(self, value):
        self.data["kwargs"] = value

    def extend_kwargs(self, values):
        self.data["kwargs"].update(values)

    @classmethod
    def generate_token(cls):
        return uuid.uuid4().hex

    @classmethod
    def load(cls, token):
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def destroy(cls, token):
        raise NotImplementedError("Implement in subclass")

    @classmethod
    def prepare(cls, backend, next_step, data):
        partial = cls()
        partial.backend = backend
        partial.next_step = next_step
        partial.data = data
        partial.token = cls.generate_token()
        return partial

    @classmethod
    def store(cls, partial):
        partial.save()
        return partial


class JSONPickler:
    """JSON pickler wrapper around json lib since SQLAlchemy invokes
    dumps with extra positional parameters"""

    @classmethod
    def dumps(cls, value, *args, **kwargs):
        """Dumps the python value into a JSON string"""
        return json.dumps(value)

    @classmethod
    def loads(cls, value):
        """Parses the JSON string and returns the corresponding python value"""
        return json.loads(value)


# JSON type field
class JSONType(PickleType):
    impl = Text

    def __init__(self, *args, **kwargs):
        kwargs["pickler"] = JSONPickler
        super().__init__(*args, **kwargs)


class SQLAlchemyMixin:
    COMMIT_SESSION = True

    @classmethod
    def _new_instance(cls, model, *args, **kwargs):
        return cls._save_instance(model(*args, **kwargs))

    @classmethod
    def _save_instance(cls, instance):
        instance_id = instance.id if hasattr(instance, "id") else None
        session = DBSession()
        session.add(instance)
        if cls.COMMIT_SESSION:
            session.commit()
            session.flush()
        else:
            try:
                session.flush()
            except AssertionError:
                session.commit()
        return (
            DBSession.query(instance.__class__).filter_by(id=instance_id).first()
            if instance_id
            else instance
        )

    def save(self):
        self._save_instance(self)


class SQLAlchemyUserMixin(SQLAlchemyMixin, UserMixin):
    """Social Auth association model"""

    __tablename__ = "social_auth_usersocialauth"
    __table_args__ = (UniqueConstraint("provider", "uid"),)
    id = Column(Integer, primary_key=True)
    provider = Column(String(32))
    uid = None
    user_id = None
    user = None

    @declared_attr
    def extra_data(cls):
        return Column(MutableDict.as_mutable(JSONType))

    @classmethod
    def changed(cls, user):
        cls._save_instance(user)

    def set_extra_data(self, extra_data=None):
        if super().set_extra_data(extra_data):
            self._save_instance(self)

    @classmethod
    def allowed_to_disconnect(cls, user, backend_name, association_id=None):
        if association_id is not None:
            qs = DBSession().query(cls).filter(cls.id != association_id)
        else:
            qs = DBSession().query(cls).filter(cls.provider != backend_name)
        qs = qs.filter(cls.user == user)

        if hasattr(user, "has_usable_password"):  # TODO
            valid_password = user.has_usable_password()
        else:
            valid_password = True
        return valid_password or qs.count() > 0

    @classmethod
    def disconnect(cls, entry):
        session = DBSession()
        session.delete(entry)
        try:
            session.flush()
        except AssertionError:
            session.commit()

    @classmethod
    def user_exists(cls, *args, **kwargs):
        """
        Return True/False if a User instance exists with the given arguments.
        Arguments are directly passed to filter() manager method.
        """
        return (
            DBSession().query(cls.user_model()).filter_by(*args, **kwargs).count() > 0
        )

    @classmethod
    def get_username(cls, user):
        return getattr(user, "username", None)

    @classmethod
    def create_user(cls, *args, **kwargs):
        return cls._new_instance(cls.user_model(), *args, **kwargs)

    @classmethod
    def get_user(cls, pk):
        return DBSession().query(cls.user_model()).filter_by(id=pk).first()

    @classmethod
    def get_users_by_email(cls, email):
        return DBSession().query(cls.user_model()).filter_by(email=email).all()

    @classmethod
    def get_social_auth(cls, provider, uid):
        if not isinstance(uid, str):
            uid = str(uid)
        try:
            return DBSession().query(cls).filter_by(provider=provider, uid=uid).first()
        except IndexError:
            return None

    @classmethod
    def get_social_auth_for_user(cls, user, provider=None, id=None):
        qs = DBSession().query(cls).filter_by(user_id=user.id)
        if provider:
            qs = qs.filter_by(provider=provider)
        if id:
            qs = qs.filter_by(id=id)
        return qs.first()

    @classmethod
    def create_social_auth(cls, user, uid, provider):
        if not isinstance(uid, str):
            uid = str(uid)
        return cls._new_instance(cls, user=user, uid=uid, provider=provider)


class SQLAlchemyNonceMixin(SQLAlchemyMixin, NonceMixin):
    __tablename__ = "social_auth_nonce"
    __table_args__ = (UniqueConstraint("server_url", "timestamp", "salt"),)
    id = Column(Integer, primary_key=True)
    server_url = Column(String(255))
    timestamp = Column(Integer)
    salt = Column(String(40))

    @classmethod
    def use(cls, server_url, timestamp, salt):
        kwargs = {"server_url": server_url, "timestamp": timestamp, "salt": salt}

        qs = DBSession().query(cls).filter_by(**kwargs).first()
        if qs is None:
            qs = cls._new_instance(cls, **kwargs)
        return qs


class SQLAlchemyAssociationMixin(SQLAlchemyMixin, AssociationMixin):
    __tablename__ = "social_auth_association"
    __table_args__ = (UniqueConstraint("server_url", "handle"),)
    id = Column(Integer, primary_key=True)
    server_url = Column(String(255))
    handle = Column(String(255))
    secret = Column(String(255))  # base64 encoded
    issued = Column(Integer)
    lifetime = Column(Integer)
    assoc_type = Column(String(64))

    @classmethod
    def store(cls, server_url, association):
        # Don't use get_or_create because issued cannot be null
        assoc = (
            DBSession()
            .query(cls)
            .filter_by(server_url=server_url, handle=association.handle)
            .first()
        )
        if assoc is None:
            assoc = cls(server_url=server_url, handle=association.handle)

        assoc.secret = base64.encodestring(association.secret).decode()
        assoc.issued = association.issued
        assoc.lifetime = association.lifetime
        assoc.assoc_type = association.assoc_type
        cls._save_instance(assoc)

    @classmethod
    def get(cls, *args, **kwargs):
        return DBSession().query(cls).filter_by(*args, **kwargs).first()

    @classmethod
    def remove(cls, ids_to_delete):
        with DBSession() as session:
            assocs = session.query(cls).filter(cls.id.in_(ids_to_delete)).all()
            for assoc in assocs:
                session.delete(assoc)
            session.commit()


class SQLAlchemyCodeMixin(SQLAlchemyMixin, CodeMixin):
    __tablename__ = "social_auth_code"
    __table_args__ = (UniqueConstraint("code", "email"),)
    id = Column(Integer, primary_key=True)
    email = Column(String(200))
    code = Column(String(32), index=True)

    @classmethod
    def get_code(cls, code):
        return DBSession().query(cls).filter_by(code=code).first()


class SQLAlchemyPartialMixin(SQLAlchemyMixin, PartialMixin):
    __tablename__ = "social_auth_partial"
    id = Column(Integer, primary_key=True)
    token = Column(String(32), index=True)
    data = Column(MutableDict.as_mutable(JSONType))
    next_step = Column(Integer)
    backend = Column(String(32))

    @classmethod
    def load(cls, token):
        return DBSession().query(cls).filter_by(token=token).first()

    @classmethod
    def destroy(cls, token):
        with DBSession() as session:
            partial = session.query(cls).filter_by(token=token).first()
            if partial:
                session.delete(partial)
                session.commit()


class TornadoStorage:
    user = None
    nonce = None
    association = None
    code = None
    partial = None

    @classmethod
    def is_integrity_error(cls, exception):
        return exception.__class__ is IntegrityError


class TornadoTemplateStrategy(BaseTemplateStrategy):
    def render_template(self, tpl, context):
        path, tpl = tpl.rsplit("/", 1)
        return Loader(path).load(tpl).generate(**context)

    def render_string(self, html, context):
        return Template(html).generate(**context)


class TornadoStrategy(BaseStrategy):
    DEFAULT_TEMPLATE_STRATEGY = TornadoTemplateStrategy

    def __init__(self, storage, request_handler, tpl=None):
        self.request_handler = request_handler
        self.request = self.request_handler.request
        super().__init__(storage, tpl)

    def get_setting(self, name):
        return self.request_handler.settings[name]

    def request_data(self, merge=True):
        # Multiple valued arguments not supported yet
        return {key: val[0].decode() for key, val in self.request.arguments.items()}

    def request_host(self):
        return self.request.host

    def redirect(self, url):
        return self.request_handler.redirect(url)

    def html(self, content):
        self.request_handler.write(content)

    def session_get(self, name, default=None):
        value = self.request_handler.get_secure_cookie(name)
        if value:
            return json.loads(value.decode())
        return default

    def session_set(self, name, value):
        self.request_handler.set_secure_cookie(name, json.dumps(value).encode())

    def session_pop(self, name):
        value = self.session_get(name)
        self.request_handler.clear_cookie(name)
        return value

    def session_setdefault(self, name, value):
        pass

    def build_absolute_uri(self, path=None):
        return build_absolute_uri(
            f"{self.request.protocol}://{self.request.host}", path
        )

    def partial_to_session(self, next, backend, request=None, *args, **kwargs):
        return json.dumps(
            super().partial_to_session(next, backend, request=request, *args, **kwargs)
        )

    def partial_from_session(self, session):
        if session:
            return super().partial_to_session(json.loads(session))


def init_social():
    class UserSocialAuth(Base, SQLAlchemyUserMixin):
        """Social Auth association model"""

        uid = Column(String(255))
        user_id = Column(User.id.type, ForeignKey(User.id), nullable=False, index=True)
        user = relationship(User, backref=backref("social_auth", lazy="dynamic"))

        @classmethod
        def username_max_length(cls):
            return User.__table__.columns.get("username").type.length

        @classmethod
        def user_model(cls):
            return User

    class Nonce(Base, SQLAlchemyNonceMixin):
        """One use numbers"""

        pass

    class Association(Base, SQLAlchemyAssociationMixin):
        """OpenId account association"""

        pass

    class Code(Base, SQLAlchemyCodeMixin):
        """Mail validation single one time use code"""

        pass

    class Partial(Base, SQLAlchemyPartialMixin):
        """Partial pipeline storage"""

        pass

    # Set the references in the storage class
    TornadoStorage.user = UserSocialAuth
    TornadoStorage.nonce = Nonce
    TornadoStorage.association = Association
    TornadoStorage.code = Code
    TornadoStorage.partial = Partial


class FakeGoogleOAuth2(GoogleOAuth2):
    @property
    def AUTHORIZATION_URL(self):
        return self.strategy.absolute_uri("/fakeoauth2/auth")

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
        return {"id": "testuser@cesium-ml.org", "email": "testuser@cesium-ml.org"}

    def get_user_id(self, *args, **kwargs):
        return "testuser@cesium-ml.org"


# Set up TornadoStorage
init_social()
