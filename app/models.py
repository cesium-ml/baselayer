from datetime import datetime
import uuid
from hashlib import md5

from slugify import slugify
import sqlalchemy as sa
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import EmailType, PhoneNumberType

from .json_util import to_json
from .custom_exceptions import AccessError


DBSession = scoped_session(sessionmaker())

# https://docs.sqlalchemy.org/en/13/dialects/postgresql.html#psycopg2-fast-execution-helpers
# executemany_values_page_size arguments control how many parameter sets
# should be represented in each execution of an INSERT
# 50000 was chosen based on recommendations in the docs and on profiling tests
EXECUTEMANY_PAGESIZE = 50000


utcnow = func.timezone('UTC', func.current_timestamp())


# The db has to be initialized later; this is done by the app itself
# See `app_server.py`
def init_db(user, database, password=None, host=None, port=None):
    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(user, password or '', host or '', port or '', database)

    conn = sa.create_engine(
        url,
        client_encoding='utf8',
        executemany_mode='values',
        executemany_values_page_size=EXECUTEMANY_PAGESIZE,
    )

    DBSession.configure(bind=conn)
    Base.metadata.bind = conn

    return conn


class SlugifiedStr(sa.types.TypeDecorator):
    """Slugified string"""

    impl = sa.String

    # Used with INSERT
    def process_bind_param(self, value, dialect):
        return slugify(value)

    # Used with SELECT
    def process_result_value(self, value, dialect):
        return value


class BaseMixin(object):
    query = DBSession.query_property()
    id = sa.Column(
        sa.Integer, primary_key=True, doc='Unique object identifier.'
    )
    created_at = sa.Column(
        sa.DateTime,
        nullable=False,
        default=utcnow,
        doc="UTC time of insertion of object's row into the database.",
    )
    modified = sa.Column(
        sa.DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        doc="UTC time the object's row was last modified in the database.",
    )

    @declared_attr
    def __tablename__(cls):
        """The name of this class's mapped database table."""
        return cls.__name__.lower() + 's'

    __mapper_args__ = {'confirm_deleted_rows': False}

    def __str__(self):
        return to_json(self)

    def __repr__(self):
        attr_list = [
            f"{c.name}={getattr(self, c.name)}" for c in self.__table__.columns
        ]
        return f"<{type(self).__name__}({', '.join(attr_list)})>"

    def to_dict(self):
        """Serialize this object to a Python dictionary."""
        if sa.inspection.inspect(self).expired:
            DBSession().refresh(self)
        return {
            k: v for k, v in self.__dict__.items() if not k.startswith('_')
        }

    @classmethod
    def get_if_owned_by(cls, ident, user_or_token, options=[]):
        """Return an object from the database if the requesting User or Token
        has access to read the object. If the requesting User or Token does not
        have access, raise an AccessError.

        Parameters
        ----------
        ident : integer or string
           Primary key of the requested object.
        user_or_token : `baselayer.app.models.User` or `baselayer.app.models.Token`
           The requesting `User` or `Token` object.
        options : list of `sqlalchemy.orm.MapperOption`s
           Options that wil be passed to `options()` in the loader query.

        Returns
        -------
        obj : baselayer.app.models.Base
           The requested entity.
        """
        obj = cls.query.options(options).get(ident)

        if obj is not None and not obj.is_owned_by(user_or_token):
            raise AccessError('Insufficient permissions.')

        return obj

    def is_owned_by(self, user_or_token):
        """Return a boolean indicating whether a User or Token has read access
        to this object.

        Parameters
        ----------
        user_or_token : `baselayer.app.models.User` or `baselayer.app.models.Token`
           The User or Token to check.

        Returns
        -------
        owned : bool
           Whether this object is readable to the user.
        """
        raise NotImplementedError("Ownership logic is application-specific")

    @classmethod
    def create_or_get(cls, id):
        """Return a new `cls` if an instance with the specified primary key
        does not exist, else return the existing instance."""
        obj = cls.query.get(id)
        if obj is not None:
            return obj
        else:
            return cls(id=id)


Base = declarative_base(cls=BaseMixin)


def join_model(
    join_table,
    model_1,
    model_2,
    column_1=None,
    column_2=None,
    fk_1='id',
    fk_2='id',
    base=Base,
):
    """Helper function to create a join table for a many-to-many relationship.

    Parameters
    ----------
    join_table : str
        Name of the new table to be created.
    model_1 : str
        First model in the relationship.
    model_2 : str
        Second model in the relationship.
    column_1 : str, optional
        Name of the join table column corresponding to `model_1`. If `None`,
        then {`table1`[:-1]_id} will be used (e.g., `user_id` for `users`).
    column_2 : str, optional
        Name of the join table column corresponding to `model_2`. If `None`,
        then {`table2`[:-1]_id} will be used (e.g., `user_id` for `users`).
    fk_1 : str, optional
        Name of the column from `model_1` that the foreign key should refer to.
    fk_2 : str, optional
        Name of the column from `model_2` that the foreign key should refer to.
    base : sqlalchemy.ext.declarative.api.DeclarativeMeta
        SQLAlchemy model base to subclass.

    Returns
    -------
    sqlalchemy.ext.declarative.api.DeclarativeMeta
        SQLAlchemy association model class
    """

    table_1 = model_1.__tablename__
    table_2 = model_2.__tablename__
    if column_1 is None:
        column_1 = f'{table_1[:-1]}_id'
    if column_2 is None:
        column_2 = f'{table_2[:-1]}_id'
    reverse_ind_name = f'{join_table}_reverse_ind'

    model_attrs = {
        '__tablename__': join_table,
        'id': None,
        column_1: sa.Column(
            column_1,
            sa.ForeignKey(f'{table_1}.{fk_1}', ondelete='CASCADE'),
            primary_key=True,
        ),
        column_2: sa.Column(
            column_2,
            sa.ForeignKey(f'{table_2}.{fk_2}', ondelete='CASCADE'),
            primary_key=True,
        ),
    }

    model_attrs.update(
        {
            model_1.__name__.lower(): relationship(
                model_1,
                cascade='save-update, merge, refresh-expire, expunge',
                foreign_keys=[model_attrs[column_1]],
            ),
            model_2.__name__.lower(): relationship(
                model_2,
                cascade='save-update, merge, refresh-expire, expunge',
                foreign_keys=[model_attrs[column_2]],
            ),
            reverse_ind_name: sa.Index(
                reverse_ind_name, model_attrs[column_2], model_attrs[column_1]
            ),
        }
    )

    model = type(model_1.__name__ + model_2.__name__, (base,), model_attrs)

    return model


class ACL(Base):
    """An access control list item representing a privilege within the
    application. Examples of ACLs include `Upload Data`, `Comment`,
    and `Manage Groups`.
    """

    id = sa.Column(
        sa.String, nullable=False, primary_key=True, doc='ACL name.'
    )


class User(Base):
    """An application user."""

    username = sa.Column(
        SlugifiedStr, nullable=False, unique=True, doc="The user's username."
    )

    first_name = sa.Column(
        sa.String, nullable=True, doc="The User's first name."
    )
    last_name = sa.Column(
        sa.String, nullable=True, doc="The User's last name."
    )
    contact_email = sa.Column(
        EmailType(),
        nullable=True,
        doc="The phone number at which the user prefers to receive "
        "communications.",
    )
    contact_phone = sa.Column(
        PhoneNumberType(),
        nullable=True,
        doc="The email at which the user prefers to receive "
        "communications.",
    )
    oauth_uid = sa.Column(
        sa.String, unique=True, doc="The user's OAuth UID."
    )

    acls = relationship(
        'ACL',
        secondary='user_acls',
        passive_deletes=True,
        doc="The ACLs granted to the User.",
    )
    tokens = relationship(
        'Token',
        cascade='save-update, merge, refresh-expire, expunge',
        back_populates='created_by',
        passive_deletes=True,
        doc="This user's tokens.",
    )
    preferences = sa.Column(
        JSONB, nullable=True, doc="The user's application settings."
    )

    @property
    def gravatar_url(self):
        """The Gravatar URL inferred from the user's contact email, or, if the
        contact email is null, the username."""
        email = (
            self.contact_email
            if self.contact_email is not None
            else self.username
        )

        digest = md5(email.lower().encode('utf-8')).hexdigest()
        # return a transparent png if not found on gravatar
        return f'https://secure.gravatar.com/avatar/{digest}?d=blank'

    @property
    def permissions(self):
        """List of the names of the user's ACLs."""
        return [acl.id for acl in self.acls]

    @classmethod
    def user_model(cls):
        """The base model for User subclasses."""
        return User

    def is_authenticated(self):
        """Boolean flag indicating whether the User is currently
        authenticated."""
        return True

    def is_active(self):
        """Boolean flag indicating whether the User is currently active."""
        return True


UserACL = join_model('user_acls', User, ACL)
UserACL.__doc__ = 'Join table mapping Users to ACLs'


class Token(Base):
    """A command line token that can be used to programmatically access the API
    as a particular User."""

    id = sa.Column(
        sa.String,
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="The value of the token. This field is used for authenticating as "
        "a User on the command line.",
    )

    created_by_id = sa.Column(
        sa.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=True,
        doc="The ID of the User that created the Token.",
    )
    created_by = relationship(
        'User', back_populates='tokens', doc="The User that created the token."
    )
    acls = relationship(
        'ACL',
        secondary='token_acls',
        passive_deletes=True,
        doc="The ACLs granted to the Token.",
    )
    name = sa.Column(
        sa.String,
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        doc="The name of the token.",
    )

    @property
    def permissions(self):
        """List of the names of the token's ACLs."""
        return [acl.id for acl in self.acls]

    def is_owned_by(self, user_or_token):
        """Return a boolean indicating whether this Token is owned by the
        specified User (or Token instance, if a token is passed).

        Parameters
        ----------
        user_or_token : `baselayer.app.models.User` or `baselayer.app.models.Token`
           The User or Token to check.

        Returns
        -------
        owned : bool
           Whether this Token instance is owned by the User or Token.
        """
        return user_or_token.id in [self.created_by_id, self.id]


TokenACL = join_model('token_acls', Token, ACL)
TokenACL.__doc__ = 'Join table mapping Tokens to ACLs'
