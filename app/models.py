import uuid
from hashlib import md5

import numpy as np

from slugify import slugify
import sqlalchemy as sa
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, aliased


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
def init_db(user, database, password=None, host=None, port=None, autoflush=True):
    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(user, password or '', host or '', port or '', database)

    conn = sa.create_engine(
        url,
        client_encoding='utf8',
        executemany_mode='values',
        executemany_values_page_size=EXECUTEMANY_PAGESIZE,
        echo=True,
    )

    DBSession.configure(bind=conn, autoflush=autoflush)
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
    """Logic for controlling user access to database records. Mapped classes
    can set their create, read, update, or delete attributes to subclasses of
    this class to ensure they are only accessed by users or tokens with the
    requisite permissions.

    This class is not meant to be instantiated. As an abstract class, it simply
    defines the interface that subclasses must implement. Only one method needs
    to be implemented by subclasses, `accessible_pairs`.
    """

    @staticmethod
    def check_cls_for_attributes(cls, attrs):
        """Check that a target class has the specified attributes. If not,
        raise a TypeError.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The class to check.
        attrs: list of str
            The names of the attributes to check for.
        """
        for attr in attrs:
            if not hasattr(cls, attr):
                raise TypeError(
                    f'{cls} does not have the attribute "{attr}", '
                    f'and thus does not expose the interface that is needed '
                    f'to check for access.'
                )

    @classmethod
    def all_pairs(cls, target_left, user_left):
        """Construct a join table mapping all target records to all user
        records (regardless of access control).

        Parameters
        ----------
        target_left: `baselayer.app.models.Base` or alias of
        `baselayer.app.models.Base`
            Access protected class or alias of the access protected class.
        user_left: `baselayer.app.models.Base` or alias of
        `baselayer.app.models.Base`
            The `User` class or an alias of the `User` class.

        Returns
        -------
        table: `sqlalchemy.sql.expression.Selectable`
            SQLalchemy table mapping all target records to all user records
            (regardless of access control).
        """
        return sa.join(target_left, user_left, sa.literal(True))

    @classmethod
    def accessible_pairs(cls, target_right, user_right):
        """Construct a join table mapping User records to accessible target
        records.

        Subclasses should implement this method to define the access control
        logic of this class.

        Parameters
        ----------
        target_right: `baselayer.app.models.Base` or alias of
        `baselayer.app.models.Base`
            Access protected class or alias of the access protected class.
        user_right: `baselayer.app.models.Base` or alias of
        `baselayer.app.models.Base`
            The `User` class or an alias of the `User` class.

        Returns
        -------
        table: `sqlalchemy.sql.expression.Selectable`
            SQLalchemy table mapping User records to accessible target records.
        """

        raise NotImplementedError

    @classmethod
    def accessibility_table(cls, target_left, target_right, user_left, user_right):
        """A join table mapping records from a table to users who can access
        them.

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

        # get all possible cls x User pairs
        all_pairs = cls.all_pairs(target_left, user_left)

        # get the accessible cls x User pairs
        accessible_pairs = cls.accessible_pairs(target_right, user_right)

        # outerjoin the two. If user_right.id is NULL, then user_left.id does
        # not have access to target_left.id. If not, then user_left.id does
        # have access to target_left.id.

        return sa.outerjoin(
            all_pairs,
            accessible_pairs,
            sa.and_(user_left.id == user_right.id, target_left.id == target_right.id),
        )


class AccessibleByAnyone(UserAccessControl):
    """A record that can be accessed by any user."""

    accessible_pairs = UserAccessControl.all_pairs


def accessible_by_user(relationship_name, of=None):
    """Create a class that grants access to only one user (and System Admins).
    For access, the user's ID must match the value of the specified foreign key.

    Parameters
    ----------
    relationship_name: str
        The name of the target class's foreign key relationship that the
        requesting user must match for access to be granted.


    Returns
    -------
    AccessibleByUser: type
        Class implementing the accessible-by-user logic.
    """

    class AccessibleByUser(UserAccessControl):
        """A record that can only be accessed by a specific user (or a System
        Admin). """

        @classmethod
        def accessible_pairs(cls, target_right, user_right):
            """Construct a join table mapping User records to accessible target
            records.

            Parameters
            ----------
            target_right: `baselayer.app.models.Base` or alias of
            `baselayer.app.models.Base`
                Access protected class or alias of the access protected class.
            user_right: `baselayer.app.models.Base` or alias of
            `baselayer.app.models.Base`
                The `User` class or an alias of the `User` class.

            Returns
            -------
            table: `sqlalchemy.sql.expression.Selectable`
                SQLalchemy table mapping User records to accessible target records.
            """

            # Ensure the target class has the foreign key that moderates
            # access control.
            cls.check_cls_for_attributes(target_right, [relationship_name])

            # Allow system admins to access the record as well as users.
            user_acls = user_acls_temporary_table()
            merged_users = sa.join(
                user_right, user_acls, user_right.id == user_acls.c.user_id
            )

            if of is not None:
                relationship = sa.inspect(target_right).mapper.relationships[of]
                class_ = relationship.argument()
                of_alias = aliased(class_)
                local_col, remote_col = relationship.local_remote_pairs[0]
                join_condition = getattr(of_alias, remote_col.name) == getattr(
                    target_right, local_col.name
                )
                final_target = target_right.join(of_alias, join_condition)
                second_relationship = sa.inspect(of_alias).mapper.relationships[
                    relationship_name
                ]
                local_col, _ = second_relationship.local_remote_pairs[0]
                cls_user_id = getattr(of_alias, local_col.name)

            else:
                final_target = target_right
                second_relationship = sa.inspect(final_target).mapper.relationships[
                    relationship_name
                ]
                local_col, _ = second_relationship.local_remote_pairs[0]
                cls_user_id = getattr(target_right, local_col.name)

            return sa.join(
                merged_users,
                final_target,
                sa.or_(
                    user_acls.c.acl_id == 'System admin', cls_user_id == user_right.id
                ),
            )

    return AccessibleByUser


AccessibleByOwner = accessible_by_user('owner')
AccessibleByCreatedBy = accessible_by_user('created_by')
AccessibleByUser = accessible_by_user('user')


def accessible_if_properties_are_accessible(**properties_and_modes):
    class AccessibleIfPropertiesAreAccessible(UserAccessControl):
        @classmethod
        def accessible_pairs(cls, target_right, user_right):
            """Construct a join table mapping User records to accessible target
            records.

            Parameters
            ----------
            target_right: `baselayer.app.models.Base` or alias of
            `baselayer.app.models.Base`
                Access protected class or alias of the access protected class.
            user_right: `baselayer.app.models.Base` or alias of
            `baselayer.app.models.Base`
                The `User` class or an alias of the `User` class.

            Returns
            -------
            table: `sqlalchemy.sql.expression.Selectable`
                SQLalchemy table mapping User records to accessible target records.
            """

            if len(properties_and_modes) == 0:
                raise ValueError("Need at least 1 property to check.")
            cls.check_cls_for_attributes(target_right, properties_and_modes)

            base = cls.all_pairs(target_right, user_right)

            for prop in properties_and_modes:
                mode = properties_and_modes[prop]
                relationship = sa.inspect(target_right).mapper.relationships[prop]
                property_class = relationship.argument()
                aliased_property_class = aliased(property_class)
                local_col, remote_col = relationship.local_remote_pairs[0]
                join_condition = getattr(
                    aliased_property_class, remote_col.name
                ) == getattr(target_right, local_col.name)

                logic = getattr(property_class, mode)
                user_alias = aliased(User)
                accessible_pairs = logic.accessible_pairs(
                    aliased_property_class, user_alias
                )

                base = base.join(
                    accessible_pairs,
                    sa.and_(join_condition, user_alias.id == user_right.id),
                )

            return base

    return AccessibleIfPropertiesAreAccessible


def compose_access_control(*access_controls):
    class ComposedAccessControl(UserAccessControl):
        @classmethod
        def accessible_pairs(cls, target_right, user_right):
            base = cls.all_pairs(target_right, user_right)

            for access_control in access_controls:

                # join against the first access control
                target_right_1 = aliased(target_right)
                user_right_1 = aliased(user_right)
                accessible_1 = access_control.accessible_pairs(
                    target_right_1, user_right_1
                )

                base = base.join(
                    accessible_1,
                    sa.and_(
                        target_right.id == target_right_1.id,
                        user_right.id == user_right_1.id,
                    ),
                )

            return base

    return ComposedAccessControl


class Restricted(UserAccessControl):
    """A record that can only be accessed by a System Admin."""

    @classmethod
    def accessible_pairs(cls, target_right, user_right):
        """Construct a join table mapping User records to accessible target
        records.

        Parameters
        ----------
        target_right: `baselayer.app.models.Base` or alias of
        `baselayer.app.models.Base`
            Access protected class or alias of the access protected class.
        user_right: `baselayer.app.models.Base` or alias of
        `baselayer.app.models.Base`
            The `User` class or an alias of the `User` class.

        Returns
        -------
        table: `sqlalchemy.sql.expression.Selectable`
            SQLalchemy table mapping User records to accessible target records.
        """
        user_acls = user_acls_temporary_table()
        merged_users = sa.join(
            user_right, user_acls, user_right.id == user_acls.c.user_id
        )
        return sa.join(
            merged_users, target_right, user_acls.c.acl_id == 'System admin',
        )


class BaseMixin:

    # permission control logic
    create = read = AccessibleByAnyone
    update = delete = Restricted

    def is_accessible_by(self, user_or_token, mode="read"):
        """Check if a User or Token has a specified type of access to this
        database record.

        Parameters
        ----------
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        mode: string
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

        target = (
            user_or_token.id
            if isinstance(user_or_token, User)
            else user_or_token.created_by_id
        )

        # get the classmethod that determines whether a record of type `cls` is
        # accessible to a user or token
        cls = type(self)
        logic = getattr(cls, mode)

        # Construct the join from which accessibility can be selected.
        user_right = aliased(User)
        user_left = aliased(User)
        target_right = aliased(cls)
        accessibility_table = logic.accessibility_table(
            cls, target_right, user_left, user_right
        )

        accessibility_target = sa.func.bool_or(user_right.id.isnot(None)).label(
            f'{mode}_ok'
        )

        # Query for the value of the access_func for this particular record and
        # return the result.
        result = (
            DBSession()
            .query(accessibility_target)
            .select_from(accessibility_table)
            .filter(cls.id == self.id, user_left.id == target)
            .group_by(cls.id, user_left.id)
            .scalar()
        )

        if not isinstance(result, bool):
            raise RuntimeError(
                f'Non-boolean result ({result}) from operation '
                f'"{type(user_or_token).__name__} {user_or_token.id} '
                f'{mode} {cls.__name__} {self.id}".'
            )

        return result

    @classmethod
    def get_if_accessible_by(
        cls, cls_id, user_or_token, mode="read", raise_if_none=False, options=[]
    ):
        """Return a database record if it is accessible to the specified User or
        Token. If no record exists, return None. If the record exists but is
        inaccessible, raise an `AccessError`.

        Parameters
        ----------
        cls_id: int, str, iterable of int, iterable of str
            The primary key(s) of the record(s) to query for.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        mode: string
            Type of access to check. Valid choices are `['create', 'read', 'update',
            'delete']`.
        options: list of `sqlalchemy.orm.MapperOption`s
           Options that will be passed to `options()` in the loader query.

        Returns
        -------
        record: `baselayer.app.models.Base` or list of `baselayer.app.models.Base`
            The requested record(s). Has the same shape as `cls_id`.
        """

        original_shape = np.asarray(cls_id).shape
        standardized = np.atleast_1d(cls_id)
        result = []

        for pk in standardized:
            instance = cls.query.options(options).get(pk.item())
            if instance is not None:
                if not instance.is_accessible_by(user_or_token, mode=mode):
                    raise AccessError(
                        f'Insufficient permissions for operation '
                        f'"{type(user_or_token).__name__} {user_or_token.id} '
                        f'{mode} {cls.__name__} {instance.id}".'
                    )
            elif raise_if_none:
                raise AccessError(f'Invalid {cls.__name__} id: {pk}')
            result.append(instance)
        return np.asarray(result).reshape(original_shape).tolist()

    @classmethod
    def get_records_accessible_by(cls, user_or_token, mode="read", options=[]):
        """Retrieve all database records accessible by the specified User or
        token.

        Parameters
        ----------
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        mode: string
            Type of access to check. Valid choices are `['create', 'read', 'update',
            'delete']`.
        options: list of `sqlalchemy.orm.MapperOption`s
           Options that will be passed to `options()` in the loader query.

        Returns
        -------
        records: list of `baselayer.app.models.Base`
            The records accessible to the specified user or token.

        """
        return cls.query_records_accessible_by(
            user_or_token, mode=mode, options=options
        ).all()

    @classmethod
    def query_records_accessible_by(cls, user_or_token, mode="read", options=[]):
        """Return the query for all database records accessible by the
        specified User or token.

        Parameters
        ----------
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        mode: string
            Type of access to check. Valid choices are `['create', 'read', 'update',
            'delete']`.
        options: list of `sqlalchemy.orm.MapperOption`s
           Options that will be passed to `options()` in the loader query.

        Returns
        -------
        query: sqlalchemy.Query
            The query for the specified records.

        """

        if not isinstance(user_or_token, (User, Token)):
            raise ValueError(
                'user_or_token must be an instance of User or Token, '
                f'got {user_or_token.__class__.__name__}.'
            )

        target = (
            user_or_token.id
            if isinstance(user_or_token, User)
            else user_or_token.created_by_id
        )

        logic = getattr(cls, mode)

        # alias User in case cls is User
        user = aliased(User)

        accessible_pairs = logic.accessible_pairs(cls, user)

        return (
            DBSession()
            .query(cls)
            .select_from(accessible_pairs)
            .filter(user.id == target)
            .options(options)
        )

    query = DBSession.query_property()
    id = sa.Column(sa.Integer, primary_key=True, doc='Unique object identifier.')
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
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

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
        'id': sa.Column(sa.Integer, primary_key=True, doc='Unique object identifier.'),
        column_1: sa.Column(
            column_1,
            sa.ForeignKey(f'{table_1}.{fk_1}', ondelete='CASCADE'),
            nullable=False,
        ),
        column_2: sa.Column(
            column_2,
            sa.ForeignKey(f'{table_2}.{fk_2}', ondelete='CASCADE'),
            nullable=False,
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
                forward_ind_name,
                model_attrs[column_1],
                model_attrs[column_2],
                unique=True,
            ),
            reverse_ind_name: sa.Index(
                reverse_ind_name, model_attrs[column_2], model_attrs[column_1]
            ),
        }
    )

    model = type(model_1.__name__ + model_2.__name__, (base,), model_attrs)
    model.read = model.create = accessible_if_properties_are_accessible(
        **{model_1.__name__.lower(): 'read', model_2.__name__.lower(): 'read'}
    )
    return model


class ACL(Base):
    """An access control list item representing a privilege within the
    application. ACLs are aggregated into collections called Roles which
    are assumed by Users. Examples of ACLs include `Upload Data`, `Comment`,
    and `Manage Groups`.
    """

    id = sa.Column(sa.String, nullable=False, primary_key=True, doc='ACL name.')


class Role(Base):
    """A collection of ACLs. Roles map Users to ACLs. One User may assume
    multiple Roles."""

    id = sa.Column(sa.String, nullable=False, primary_key=True, doc='Role name.')
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

    first_name = sa.Column(sa.String, nullable=True, doc="The User's first name.")
    last_name = sa.Column(sa.String, nullable=True, doc="The User's last name.")
    contact_email = sa.Column(
        EmailType(),
        nullable=True,
        doc="The phone number at which the user prefers to receive " "communications.",
    )
    contact_phone = sa.Column(
        PhoneNumberType(),
        nullable=True,
        doc="The email at which the user prefers to receive " "communications.",
    )
    oauth_uid = sa.Column(sa.String, unique=True, doc="The user's OAuth UID.")
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
    role_ids = association_proxy('roles', 'id', creator=lambda r: Role.query.get(r),)
    tokens = relationship(
        'Token',
        cascade='save-update, merge, refresh-expire, expunge',
        back_populates='created_by',
        passive_deletes=True,
        doc="This user's tokens.",
        foreign_keys="Token.created_by_id",
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
        email = self.contact_email if self.contact_email is not None else self.username

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
            {acl.id for acl in self.acls}.union(
                {acl.id for acl in self._acls_from_roles}
            )
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
    acl_ids = association_proxy('acls', 'id', creator=lambda acl: ACL.query.get(acl))
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
