import abc
import uuid
from hashlib import md5

from slugify import slugify
import sqlalchemy as sa
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, Query, aliased
from sqlalchemy.sql.expression import Selectable, BinaryExpression, FromClause
from sqlalchemy.ext.hybrid import hybrid_method


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


def user_acls_temporary_table():
    """This method creates a temporary table that maps user_ids to their
    acl_ids (from roles and individual ACL grants).

    The temporary table lives for the duration of the current database
    transaction and is visible only to the transaction it was created
    within. The temporary table maintains a forward and reverse index
    for fast joins on accessible groups.

    This function can be called many times within a transaction. It will only
    create the table once per transaction and subsequent calls will always
    return a reference to the table created on the first call, with the same
    underlying data.

    Returns
    -------
    table: `sqlalchemy.Table`
        The forward- and reverse-indexed `merged_user_acls` temporary
        table for the current database transaction.
    """
    sql = """CREATE TEMP TABLE IF NOT EXISTS merged_user_acls ON COMMIT DROP AS
    (SELECT u.id AS user_id, ra.acl_id AS acl_id
         FROM users u
         JOIN user_roles ur ON u.id = ur.user_id
         JOIN role_acls ra ON ur.role_id = ra.role_id
         UNION
     SELECT ua.user_id, ua.acl_id FROM user_acls ua)"""
    DBSession().execute(sql)
    DBSession().execute(
        'CREATE INDEX IF NOT EXISTS merged_user_acls_forward_index '
        'ON merged_user_acls (user_id, acl_id)'
    )
    DBSession().execute(
        'CREATE INDEX IF NOT EXISTS merged_user_acls_reverse_index '
        'ON merged_user_acls (acl_id, user_id)'
    )

    t = sa.Table(
        'merged_user_acls',
        Base.metadata,
        sa.Column('user_id', sa.Integer, primary_key=True),
        sa.Column('acl_id', sa.Integer, primary_key=True),
        extend_existing=True,
    )
    return t


class UserAccessControl:
    """Logic for restricting user access to database records. Mapped classes
    can set their create, read, update, or delete attributes to subclasses of
    this class to ensure they are only accessed by users or tokens with the
    requisite permissions.

    This class is not meant to be instantiated. As an abstract class, it simply
    defines the interface that subclasses must implement.
    """

    # Attributes that a mapped class must have to call `access_table()`.
    required_attrs = NotImplemented

    @staticmethod
    def access_table(cls, user) -> FromClause:
        """A join table mapping records from a table to users who can access
        them. Subclasses of AccessControl must implement this method
        with the appropriate logic.

        The join table should be constructed using aliases of `cls` and `user`,
        then correlated against `cls` and `user` to ensure indices are propagated
        and Cardinality is respected.

        Parameters
        ----------
        cls: mapped class or alias of mapped class
            The mapped class (or an alias of the mapped class) representing the
            access-controlled table.
        user: User class or alias of User class
            The User class (or an alias of the User class).

        Returns
        -------
        access_table: sqlalchemy.sql.expression.FromClause
            A join table mapping records of the `cls` table to records
            of the users table. Each row corresponds to one class/user pair that
            is accessible. The schema of this table may vary depending on the
            schema of `cls`, but will always contain two columns, `cls_id` and
            `user_id`, representing the primary keys of the `cls` table and the
            users table, respectively.
        """
        return NotImplementedError


class AccessibleByAnyone(UserAccessControl):
    """A record that can be accessed by any user."""

    required_attrs = ()

    @staticmethod
    def access_table(cls, user):
        """A join table mapping records from a table to users who can access
        them. Subclasses of AccessControlPattern must implement this method
        with the appropriate logic.

        The join table should be constructed using aliases of `cls` and `user`,
        then correlated against `cls` and `user` to ensure indices are propagated
        and Cardinality is respected.

        Parameters
        ----------
        cls: mapped class or alias of mapped class
            The mapped class (or an alias of the mapped class) representing the
            access-controlled table.
        user: User class or alias of User class
            The User class (or an alias of the User class).

        Returns
        -------
        access_table: sqlalchemy.sql.expression.FromClause
            A join table mapping records of the `cls` table to records
            of the users table. Each row corresponds to one class/user pair that
            is accessible. The schema of this table may vary depending on the
            schema of `cls`, but will always contain two columns, `cls_id` and
            `user_id`, representing the primary keys of the `cls` table and the
            users table, respectively.
        """
        cls_alias = aliased(cls)
        user_alias = aliased(user)
        return (
            sa.select(
                [cls_alias.id.label('cls_id'), user_alias.id.label('user_id')]
            )
            .select_from(sa.join(cls_alias, user_alias, sa.literal(True)))
            .where(cls_alias.id == cls.id)
            .where(user_alias.id == user.id)
        )


def accessible_through_relationship(relationship_name, fk_name):

    class AccessibleByUser(UserAccessControl):
        """A record that can only be accessed by a specific user (or a System Admin)."""

        required_attrs = (relationship_name,)

        @staticmethod
        def access_table(cls, user):
            """A join table mapping records from a table to users who can access
            them. Subclasses of AccessControlPattern must implement this method
            with the appropriate logic.

            The join table should be constructed using aliases of `cls` and `user`,
            then correlated against `cls` and `user` to ensure indices are propagated
            and Cardinality is respected.

            Parameters
            ----------
            cls: mapped class or alias of mapped class
                The mapped class (or an alias of the mapped class) representing the
                access-controlled table.
            user: User class or alias of User class
                The User class (or an alias of the User class).

            Returns
            -------
            access_table: sqlalchemy.sql.expression.FromClause
                A join table mapping records of the `cls` table to records
                of the users table. Each row corresponds to one class/user pair that
                is accessible. The schema of this table may vary depending on the
                schema of `cls`, but will always contain two columns, `cls_id` and
                `user_id`, representing the primary keys of the `cls` table and the
                users table, respectively.
            """
            cls_alias = aliased(cls)
            user_alias = aliased(user)
            user_acls = user_acls_temporary_table()
            user_id = getattr(cls_alias, fk_name)

            accessible_by_virtue_of_owner = (
                sa.select(
                    [cls_alias.id.label('cls_id'), user_alias.id.label('user_id')]
                )
                .select_from(
                    sa.join(cls_alias, user_alias, user_id == user_alias.id)
                )
                .where(cls_alias.id == cls.id)
                .where(user_alias.id == user.id)
            )

            accessible_by_virtue_of_acl = (
                sa.select([cls_alias.id, user_acls.user_id])
                .select_from(
                    sa.join(cls, user_acls, user_acls.acl_id == 'System admin', )
                )
                .where(cls_alias.id == cls.id)
                .where(user_acls.user_id == user.id)
            )

            return sa.union(accessible_by_virtue_of_owner, accessible_by_virtue_of_acl)
    return AccessibleByUser


AccessibleByOwner = accessible_through_relationship('owner', 'owner_id')
AccessibleByCreatedBy = accessible_through_relationship('created_by', 'created_by_id')
AccessibleByUser = accessible_through_relationship('user', 'user_id')



class Inaccessible(UserAccessControl):
    """A record that can only be accessed by a System Admin."""

    required_attrs = ()

    @staticmethod
    def access_table(cls, user):
        """A join table mapping records from a table to users who can access
        them. Subclasses of AccessControlPattern must implement this method
        with the appropriate logic.

        The join table should be constructed using aliases of `cls` and `user`,
        then correlated against `cls` and `user` to ensure indices are propagated
        and Cardinality is respected.

        Parameters
        ----------
        cls: mapped class or alias of mapped class
            The mapped class (or an alias of the mapped class) representing the
            access-controlled table.
        user: User class or alias of User class
            The User class (or an alias of the User class).

        Returns
        -------
        access_table: sqlalchemy.sql.expression.FromClause
            A join table mapping records of the `cls` table to records
            of the users table. Each row corresponds to one class/user pair that
            is accessible. The schema of this table may vary depending on the
            schema of `cls`, but will always contain two columns, `cls_id` and
            `user_id`, representing the primary keys of the `cls` table and the
            users table, respectively.
        """
        cls_alias = aliased(cls)
        user_acls = user_acls_temporary_table()

        accessible_by_virtue_of_acl = (
            sa.select([cls_alias.id, user_acls.user_id])
            .select_from(
                sa.join(cls, user_acls, user_acls.acl_id == 'System admin', )
            )
            .where(cls_alias.id == cls.id)
            .where(user_acls.user_id == user.id)
        )

        return accessible_by_virtue_of_acl.distinct()


class BaseMixin:

    # permission control logic
    create = read = AccessibleByAnyone
    update = delete = Inaccessible

    @hybrid_method
    def is_accessible_by(self, user_or_token, access_type="read") -> bool:
        """Determines whether a User or Token has a specified type of access to
        a database record.

        Parameters
        ----------
        self: `baselayer.app.models.Base`:
            The instance to check the User or Token's access to. Must be in the
            SQLalchemy "persistent" state (https://docs.sqlalchemy.org/en/13/\
            orm/session_state_management.html#quickie-intro-to-object-states)
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        access_type: string
            Type of access to check. Valid choices are `['create', 'read', 'update',
            'delete']`.
        Returns
        -------
        accessible: bool
            Whether the User or Token has the specified type of access to
            the record.
        """

        if not isinstance(user_or_token, (User, Token)):
            raise ValueError(
                'user_or_token must be an instance of User or Token, '
                f'got {user_or_token.__class__.__name__}.'
            )

        # get the classmethod that determines whether a record of type `cls` is
        # accessible to a user or token
        cls = type(self)

        # Query for the value of the access_func for this particular record and
        # return the result.
        return (
            DBSession()
            .query(cls.is_accessible_by(user_or_token, access_type=access_type))
            .filter(cls.id == self.id)
            .scalar()
        )

    @classmethod
    def get_if_accessible_by(
        cls, cls_id, user_or_token, access_type="read", options=[]
    ):
        """Return a database record if it is accessible to the specified User or
        Token. If no record exists, return None. If the record exists but is
        inaccessible, raise an `AccessError`.

        Parameters
        ----------
        cls_id: int or str
            The primary key of the record to query for.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        access_type: string
            Type of access to check. Valid choices are `['create', 'read', 'update',
            'delete']`.
        options: list of `sqlalchemy.orm.MapperOption`s
           Options that will be passed to `options()` in the loader query.

        Returns
        -------
        record: `baselayer.app.models.Base`
            The requested record.
        """

        instance = cls.query.options(options).get(cls_id)
        if instance is not None:
            if not instance.is_accessible_by(user_or_token, access_type=access_type):
                raise AccessError(
                    f'Insufficient permissions for operation '
                    f'"{access_type} {cls.__name__} {instance.id}".'
                )
        return instance

    @classmethod
    def query_for_records_accessible_by(cls, user_or_token, access_type="read", options=[]):
        """Construct (but do not execute) a database query to retrieve all records
        that are accessible to a single user or token from a specified table.

        The query is based on join-dependent relationship hybrid logic,
        (https://docs.sqlalchemy.org/en/14/orm/extensions/hybrid.html?highlight=\
        hybrid%20method#join-dependent-relationship-hybrid),
        rather than correlated subquery hybrid logic. This gives it better
        performance compared to the correlated subquery-based hybrid methods
        `is_*_by`, but a more restricted range of uses.

        Parameters
        ----------
        cls: DeclarativeMeta
            Mapped class to query for records. Must be a subclass of Base.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        access_type: string
            Type of access to check. Valid choices are `['create', 'read', 'update',
            'delete']`.
        options: list of `sqlalchemy.orm.MapperOption`s
           Options that will be passed to `options()` in the loader query.
        Returns
        -------
        query: `sqlalchemy.orm.Query`
           The query for accessible records.
        """

        logic = getattr(cls, access_type)
        for attr in logic.required_attrs:
            if not hasattr(cls, attr):
                raise TypeError(
                    f'{cls} does not have the attribute "{attr}", '
                    f'and thus does not expose the interface that is needed '
                    f'to check for {access_type} access.'
                )

        if isinstance(user_or_token, User):
            accessibility_target = user_or_token.id
        elif isinstance(user_or_token, Token):
            accessibility_target = user_or_token.created_by_id
        else:
            raise TypeError(
                f'Invalid argument passed to user_or_token, '
                f'expected User or Token, got '
                f'{user_or_token.__class__.__name__}'
            )

        # Construct a query that maps user_ids to accessible cls_ids.
        pairs = logic.access_table(cls, User).alias()

        return (
            DBSession()
            .query(cls)
            .join(User, sa.literal(True))
            .join(pairs, sa.and_(User.id == pairs.c.user_id, cls.id == pairs.c.cls_id))
            .filter(User.id == accessibility_target)
            .options(options)
        )

    @is_accessible_by.expression
    def is_accessible_by(cls, user_or_token, access_type="read") -> BinaryExpression:
        """Generate an SQL expression representing whether a mapped class is
        accessible to a specified user or token, or to an entire table of users
        or tokens (via broadcasting).

        The expressions can be queried directly,

            >>> u = User.query.first()
            >>> DBSession().query(cls.is_accessible_by(u))

        or used as filter clauses,

            >>> u = User.query.first()
            >>> DBSession().query(cls).filter(cls.is_accessible_by(u))

        or used as join clauses,

            >>> DBSession().query(cls).join(User, cls.is_accessible_by(User))

        The BinaryExpression is designed to be highly portable and is constructed
        using correlated subquery relationship hybrids and laterals. This ensures
        that large intermediate tables are never created, that indices are used
        wherever possible, and that filter clauses from enclosing queries are
        always propagated down the query stack.

        Parameters
        ----------
        cls: DeclarativeMeta
            Mapped class to query for records. Must be a subclass of Base.
        user_or_token: `baselayer.app.models.User`, `baselayer.app.models.Token`,
        `sqlalchmey.sql.expression.FromClause`, `sqlalchemy.Column`
            The User, Token, or table to check. Can be a User or Token object,
            a reference to an `sqlalchemy.Table` pointing to the users or tokens
            table, or an `sqlalchemy.Column` containing the primary key of the
            users table.
        access_type: string, required:
            Type of access to check. Valid choices are `['create', 'read',
            'update', 'delete']`.

        Returns
        -------
        accessible: `sqlalchemy.sql.expression.BinaryExpression`
            SQLalchemy expression representing whether the User, Token, or table
            has access to the record. Can be queried directly, or used as a filter
            or join clause.
        """

        # Ensure that the constructed class has the required attributes for
        # access check.

        logic = getattr(cls, access_type)
        for attr in logic.required_attrs:
            if not hasattr(cls, attr):
                raise TypeError(
                    f'{cls.__name__} does not have the attribute "{attr}", '
                    f'and thus does not expose the interface that is needed '
                    f'to check for {access_type} access.'
                )

        # Extract the users.id column from whatever was passed to `user_or_token`.
        if isinstance(user_or_token, FromClause):
            if hasattr(user_or_token.c, 'created_by_id'):
                accessibility_target = user_or_token.c.created_by_id
            else:
                accessibility_target = user_or_token.c.id
        elif isinstance(user_or_token, sa.Column):
            accessibility_target = user_or_token
        elif user_or_token is Token or isinstance(user_or_token, Token):
            accessibility_target = user_or_token.created_by_id
        else:
            accessibility_target = user_or_token.id

        correlation_cls_alias = aliased(cls)
        correlation_user_alias = aliased(User)
        accessible_pairs = logic.access_table(
            correlation_cls_alias, correlation_user_alias
        ).lateral()

        return (
            sa.select([accessible_pairs.c.cls_id])
            .select_from(
                sa.join(
                    correlation_cls_alias, correlation_user_alias, sa.literal(True)
                ).outerjoin(
                    accessible_pairs,
                    correlation_cls_alias.id == accessible_pairs.c.cls_id,
                )
            )
            .where(correlation_cls_alias.id == cls.id)
            .where(correlation_user_alias.id == accessibility_target)
            .label(access_type)
            .isnot(None)
        )

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

    forward_ind_name = f'{join_table}_forward_ind'
    reverse_ind_name = f'{join_table}_reverse_ind'

    model_attrs = {
        '__tablename__': join_table,
        'id': sa.Column(
            sa.Integer, primary_key=True, doc='Unique object identifier.'
        ),
        column_1: sa.Column(
            column_1,
            sa.ForeignKey(f'{table_1}.{fk_1}', ondelete='CASCADE'),
            nullable=False
        ),
        column_2: sa.Column(
            column_2,
            sa.ForeignKey(f'{table_2}.{fk_2}', ondelete='CASCADE'),
            nullable=False
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
            forward_ind_name: sa.Index(
                forward_ind_name, model_attrs[column_1], model_attrs[column_2],
                unique=True
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
    application. ACLs are aggregated into collections called Roles which
    are assumed by Users. Examples of ACLs include `Upload Data`, `Comment`,
    and `Manage Groups`.
    """

    id = sa.Column(
        sa.String, nullable=False, primary_key=True, doc='ACL name.'
    )


class Role(Base):
    """A collection of ACLs. Roles map Users to ACLs. One User may assume
    multiple Roles."""

    id = sa.Column(
        sa.String, nullable=False, primary_key=True, doc='Role name.'
    )
    acls = relationship(
        'ACL',
        secondary='role_acls',
        passive_deletes=True,
        doc='ACLs associated with the Role.',
    )
    users = relationship(
        'User',
        secondary='user_roles',
        back_populates='roles',
        passive_deletes=True,
        doc='Users who have this Role.',
    )


RoleACL = join_model('role_acls', Role, ACL)
RoleACL.__doc__ = "Join table class mapping Roles to ACLs."


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
    preferences = sa.Column(
        JSONB, nullable=True, doc="The user's application settings."
    )

    roles = relationship(
        'Role',
        secondary='user_roles',
        back_populates='users',
        passive_deletes=True,
        doc='The roles assumed by this user.',
    )
    role_ids = association_proxy(
        'roles',
        'id',
        creator=lambda r: Role.query.get(r),
    )
    tokens = relationship(
        'Token',
        cascade='save-update, merge, refresh-expire, expunge',
        back_populates='created_by',
        passive_deletes=True,
        doc="This user's tokens.",
        foreign_keys="Token.created_by_id"
    )
    acls = relationship(
        "ACL",
        secondary="user_acls",
        passive_deletes=True,
        doc="ACLs granted to user, separate from role-level ACLs",
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
    def _acls_from_roles(self):
        """List of the ACLs associated with the user's role(s)."""
        return list({acl for role in self.roles for acl in role.acls})

    @property
    def permissions(self):
        """List of the names of all of the user's ACLs (role-level + individual)."""
        return list(
            {acl.id for acl in self.acls}
            .union({acl.id for acl in self._acls_from_roles})
        )

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
    create = read = update = delete = AccessibleByCreatedBy

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
    acl_ids = association_proxy(
        'acls',
        'id',
        creator=lambda acl: ACL.query.get(acl)
    )
    permissions = acl_ids

    name = sa.Column(
        sa.String,
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        doc="The name of the token.",
    )


TokenACL = join_model('token_acls', Token, ACL)
TokenACL.__doc__ = 'Join table mapping Tokens to ACLs'
UserRole = join_model('user_roles', User, Role)
UserRole.__doc__ = 'Join table mapping Users to Roles.'


