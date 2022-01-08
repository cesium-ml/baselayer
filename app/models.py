from datetime import datetime
import uuid
import contextvars
from hashlib import md5
import warnings

import numpy as np
import sqlalchemy as sa
import traceback
import requests
from slugify import slugify
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy_utils import EmailType, PhoneNumberType

from .custom_exceptions import AccessError
from .json_util import to_json
from .env import load_env

session_context_id = contextvars.ContextVar("request_id", default=None)
DBSession = scoped_session(sessionmaker(), scopefunc=session_context_id.get)

env, cfg = load_env()
strict = cfg["security.strict"]
use_webhook = cfg["security.slack.enabled"]
webhook_url = cfg["security.slack.url"]


def handle_inaccessible(mode, row_ids, row_type, accessor):
    tb = "".join(traceback.extract_stack().format())
    tb = f"```{tb}```"

    err_msg = (
        f"Insufficient permissions for operation "
        f'"{type(accessor).__name__} {accessor.id} '
        f'{mode} {row_type.__name__} {row_ids}".'
    )
    err_msg_w_traceback = err_msg + f"Original traceback: {tb}"

    if use_webhook:
        try:
            requests.post(webhook_url, json={"text": err_msg_w_traceback})
        except requests.HTTPError as e:
            post_fail_warn_msg = (
                f'Encountered HTTPError "{e.args[0]}" '
                f'attempting to post AccessError "{err_msg}"'
                f"to {webhook_url}."
            )
            warnings.warn(post_fail_warn_msg)
    else:
        warnings.warn(err_msg)
    if strict:
        raise AccessError(err_msg)


# https://docs.sqlalchemy.org/en/13/dialects/postgresql.html#psycopg2-fast-execution-helpers
# executemany_values_page_size arguments control how many parameter sets
# should be represented in each execution of an INSERT
# 50000 was chosen based on recommendations in the docs and on profiling tests
EXECUTEMANY_PAGESIZE = 50000


utcnow = func.timezone("UTC", func.current_timestamp())


# The db has to be initialized later; this is done by the app itself
# See `app_server.py`
def init_db(
    user,
    database,
    password=None,
    host=None,
    port=None,
    autoflush=True,
    engine_args={},
):
    """
    Parameters
    ----------
    engine_args : dict
        - `pool_size`:
          The number of connections maintained to the DB. Default 5.

        - `max_overflow`:
          The number of additional connections that will be made as needed.
           Once these extra connections have been used, they are discarded.
          Default 10.

        - `pool_recycle`:
           Prevent the pool from using any connection that is older than this
           (specified in seconds).
           Default 3600.

    """
    url = "postgresql://{}:{}@{}:{}/{}"
    url = url.format(user, password or "", host or "", port or "", database)

    default_engine_args = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 3600,
    }
    conn = sa.create_engine(
        url,
        client_encoding="utf8",
        executemany_mode="values",
        executemany_values_page_size=EXECUTEMANY_PAGESIZE,
        **{**default_engine_args, **engine_args},
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


class UserAccessControl:
    """Logic for controlling user access to database records. Mapped classes
    can set their create, read, update, or delete attributes to subclasses of
    this class to ensure they are only accessed by users or tokens with the
    requisite permissions.
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
                    f"and thus does not expose the interface that is needed "
                    f"to check for access."
                )

    @staticmethod
    def user_id_from_user_or_token(user_or_token):
        """Return the user_id associated with a specified User or Token object.

        Parameters
        ----------
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.

        Returns
        -------
        user_id: int
            The user_id associated with the User or Token object.
        """
        if isinstance(user_or_token, User):
            return user_or_token.id
        elif isinstance(user_or_token, Token):
            return user_or_token.created_by_id
        else:
            raise ValueError(
                "user_or_token must be an instance of User or Token, "
                f"got {user_or_token.__class__.__name__}."
            )

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """

        raise NotImplementedError

    def __and__(self, other):
        """Return a policy that is the logical AND of two UserAccessControls.

        Parameters
        ----------
        other: UserAccessControl
            The access control to combine with this one.

        Returns
        -------
        composed: ComposedAccessControl
            The UserAccessControl representing the logical AND of the input access
            controls.


        Examples
        --------
        Create an access control that grants access if the querying user is the record
        owner AND the user that most recently modified the record

            >>>> accessible_if_is_owner = AccessibleIfUserMatches('owner')
            >>>> accessible_if_is_last_modifier = AccessibleIfUserMatches('last_modified_by')
            >>>> access_control = accessible_if_is_owner & accessible_if_is_last_modifier
        """

        try:
            retval = ComposedAccessControl(self, other, logic="and")
        except TypeError:
            raise TypeError(
                f"unsupported operand type(s) for &: '{type(self).__name__}' "
                f"and '{type(other).__name__}'"
            )
        return retval

    def __or__(self, other):
        """Return a policy that is the logical OR of two UserAccessControls.

        Parameters
        ----------
        other: UserAccessControl
            The access control to combine with this one.

        Returns
        -------
        composed: ComposedAccessControl
            The UserAccessControl representing the logical OR of the input access
            controls.


        Examples
        --------
        Create an access control that grants access if the querying user is the record
        owner OR the user that most recently modified the record

            >>>> accessible_if_is_owner = AccessibleIfUserMatches('owner')
            >>>> accessible_if_is_last_modifier = AccessibleIfUserMatches('last_modified_by')
            >>>> access_control = accessible_if_is_owner | accessible_if_is_last_modifier
        """
        try:
            retval = ComposedAccessControl(self, other, logic="or")
        except TypeError:
            raise TypeError(
                f"unsupported operand type(s) for |: '{type(self).__name__}' "
                f"and '{type(other).__name__}'"
            )
        return retval


class Public(UserAccessControl):
    """A record accessible to anyone."""

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """
        if columns is not None:
            return DBSession().query(*columns).select_from(cls)
        return DBSession().query(cls)


public = Public()


class AccessibleIfUserMatches(UserAccessControl):
    def __init__(self, relationship_chain):
        """A class that grants access to users related to a specific record
        through a chain of relationships.

        Parameters
        ----------
        relationship_chain: str
            The chain of relationships to check the User or Token against in
            `query_accessible_rows`. Should be specified as

            >>>> f'{relationship1_name}.{relationship2_name}...{relationshipN_name}'

            The first relationship should be defined on the target class, and
            each subsequent relationship should be defined on the class pointed
            to by the previous relationship. If the querying user matches any
            record pointed to by the final relationship, the logic will grant
            access to the querying user.

        Examples
        --------

        Grant access if the querying user matches the user pointed to by
        the target class's `author` relationship:

            >>>> AccessibleIfUserMatches('author')

        Grant access if the querying user is a member of one of the target
        class's groups:

            >>>> AccessibleIfUserMatches('groups.users')
        """
        self.relationship_chain = relationship_chain

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """

        # system admins automatically get full access
        if user_or_token.is_admin:
            return public.query_accessible_rows(
                cls, user_or_token, columns=columns
            )

        # return only selected columns if requested
        if columns is not None:
            query = DBSession().query(*columns).select_from(cls)
        else:
            query = DBSession().query(cls)

        # traverse the relationship chain via sequential JOINs
        for relationship_name in self.relationship_names:
            self.check_cls_for_attributes(cls, [relationship_name])
            relationship = sa.inspect(cls).mapper.relationships[
                relationship_name
            ]

            # not a private attribute, just has an underscore to avoid name
            # collision with python keyword
            cls = relationship.entity.class_

            query = query.join(relationship.class_attribute)

        # filter for records with at least one matching user
        user_id = self.user_id_from_user_or_token(user_or_token)
        query = query.filter(cls.id == user_id)
        return query

    @property
    def relationship_chain(self):
        return self._relationship_key

    @relationship_chain.setter
    def relationship_chain(self, value):
        """Validate the formatting for passed relationship chains, raise when
        users attempt to pass incorrectly formatted chain strings."""
        if not isinstance(value, str):
            raise ValueError(
                f"Invalid value for relationship chain: {value}, expected str, "
                f"got {value.__class__.__name__}"
            )
        relationship_names = value.split(".")
        if len(relationship_names) < 1:
            raise ValueError("Need at least 1 relationship to join on.")
        self._relationship_key = value

    @property
    def relationship_names(self):
        """List of names of each relationship in the chain."""
        return self.relationship_chain.split(".")


accessible_by_owner = AccessibleIfUserMatches("owner")
accessible_by_created_by = AccessibleIfUserMatches("created_by")
accessible_by_user = AccessibleIfUserMatches("user")


class AccessibleIfRelatedRowsAreAccessible(UserAccessControl):
    def __init__(self, **properties_and_modes):
        """A class that grants access to users only if related rows are also
        accessible to those users. This class automatically grants access to
        Users with the "System admin" ACL.

        Parameters
        ----------
        properties_and_modes: dict
            Dict mapping relationship names to access types (e.g., 'create',
            'read', 'update', 'delete'). In order for a user to access a record
            protected with this logic, they must be able to access the records
            pointed to by the relationship with the specified type of access.

        Examples
        --------

        Grant access if the querying user can read the "created_by" record
        pointed to by a target record:

            >>>> AccessibleIfRelatedRowsAreAccessible(created_by="read")

        Grant access if the querying user can read the "created_by" and update
        the "last_modified_by" records pointed to by a target record:

            >>>> AccessibleIfRelatedRowsAreAccessible(created_by="read", last_modified_by="update")

        """
        self.properties_and_modes = properties_and_modes

    @property
    def properties_and_modes(self):
        return self._properties_and_modes

    @properties_and_modes.setter
    def properties_and_modes(self, value):
        """Validate that properties and modes are correctly specified,
        raise if not."""
        if not isinstance(value, dict):
            raise ValueError(
                f"properties_and_modes must be an instance of dict, "
                f"got {value.__class__.__name__}"
            )
        if len(value) == 0:
            raise ValueError("Need at least 1 property to check.")
        self._properties_and_modes = value

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """

        # only return specified columns if requested
        if columns is None:
            base = DBSession().query(cls)
        else:
            base = DBSession().query(*columns).select_from(cls)

        # ensure the target class has all the relationships referred to
        # in this instance
        self.check_cls_for_attributes(cls, self.properties_and_modes)

        # construct the list of accessible records by joining the target
        # table against accessible related rows via their relationships
        # to the target table
        for prop in self.properties_and_modes:

            # get the kind of access required on the relationship
            mode = self.properties_and_modes[prop]
            relationship = sa.inspect(cls).mapper.relationships[prop]

            # get the rows of the target table that are accessible
            join_target = relationship.entity.class_
            logic = getattr(join_target, mode)

            if isinstance(logic, Public):
                continue

            # join the target table to the related table on the relationship
            base = base.join(relationship.class_attribute)

            # create a subquery for the accessible rows of the related table
            # and join that subquery to the related table on the PK/FK.
            # from a performance perspective this should be about as performant
            # as aliasing the related table. The subquery is automatically
            # de-subbed by postgres and uses all available indices.

            accessible_related_rows = logic.query_accessible_rows(
                join_target, user_or_token, columns=[join_target.id]
            ).subquery()

            join_condition = accessible_related_rows.c.id == join_target.id
            base = base.join(accessible_related_rows, join_condition)

        return base


class ComposedAccessControl(UserAccessControl):
    def __init__(self, *access_controls, logic="and"):
        """A policy that is the logical AND or logical OR of other
        UserAccessControls.

        Parameters
        ----------
        access_controls: list of `UserAccessControl`
            The access controls to compose.
        logic: "and" or "or", default "and"
            How to combine the access controls. If "and", all conditions must
            be satisfied for access to be granted. If "or", only one of the
            conditions must be satisfied for access to be granted.

        Examples
        --------

        Grant access if the querying user matches the 'owner' relationship of
        this record or if the querying user is a member of at least one of the
        record's groups:

            >>>> ComposedAccessControl(AccessibleIfUserMatches('owner'), AccessibleIfUserMatches('groups.users'), logic='or')
        """
        self.access_controls = access_controls
        self.logic = logic

    @property
    def access_controls(self):
        return self._access_controls

    @access_controls.setter
    def access_controls(self, value):
        """Validate the input access controls."""
        error = ValueError(
            f"access_controls must be a list or tuple of "
            f"UserAccessControl, got {value.__class__.__name__}"
        )
        if not isinstance(value, (list, tuple)):
            raise error
        for v in value:
            if not isinstance(v, UserAccessControl):
                raise error
        self._access_controls = value

    @property
    def logic(self):
        return self._logic

    @logic.setter
    def logic(self, value):
        """Validate the input logic."""
        if value not in ["and", "or"]:
            raise ValueError(
                f'composition logic must be either "and" or "or", got {value}.'
            )
        self._logic = value

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """

        # retrieve specified columns if requested
        if columns is not None:
            query = DBSession().query(*columns).select_from(cls)
        else:
            query = DBSession().query(cls)

        # keep track of columns that will be null in the case of an unsuccessful
        # match for OR logic.
        accessible_id_cols = []

        for access_control in self.access_controls:

            # Just ignore public ACLs
            if isinstance(access_control, Public):
                continue

            # use an alias to avoid name collisions.
            # target_alias = sa.orm.aliased(cls)

            # join against the first access control using a subquery. from a
            # performance perspective this should be about as performant as
            # aliasing the related table, but is much better for avoiding
            # name collisions. The subquery is automatically de-subbed by
            # postgres and uses all available indices.
            accessible = access_control.query_accessible_rows(
                cls, user_or_token, columns=[cls.id]
            ).subquery()

            # join on the FK
            join_condition = accessible.c.id == cls.id
            if self.logic == "and":
                # for and logic, we want an INNER join
                query = query.join(accessible, join_condition)
            elif self.logic == "or":
                # for OR logic we dont want to lose rows where there is no
                # for one particular type of access control, so use outer join
                # here
                query = query.outerjoin(accessible, join_condition)
            else:
                raise ValueError(
                    f'Invalid composition logic: {self.logic}, must be either "and" or "or".'
                )
            accessible_id_cols.append(accessible.c.id)

        # in the case of or logic, require that only one of the conditions be
        # met for each row
        if self.logic == "or":
            query = query.filter(
                sa.or_(*[col.isnot(None) for col in accessible_id_cols])
            )

        return query


class Restricted(UserAccessControl):
    """A record that can only be accessed by a System Admin."""

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """

        # system admins have access to restricted records
        if user_or_token.is_admin:
            return public.query_accessible_rows(
                cls, user_or_token, columns=columns
            )

        # otherwise, all records are inaccessible
        if columns is not None:
            return (
                DBSession()
                .query(*columns)
                .select_from(cls)
                .filter(sa.literal(False))
            )
        return DBSession().query(cls).filter(sa.literal(False))


restricted = Restricted()


class CustomUserAccessControl(UserAccessControl):
    def __init__(self, query_or_query_generator):
        """A UserAccessControl that uses explicit, user-provided logic to
        designate accessible records.

        Parameters
        ----------
        query_or_query_generator: `sqlalchemy.orm.Query` or func

            The logic for determining which records are accessible to a
            user.

            In cases where the access control logic is the same for all
            users, this class can be directly initialized from an SQLAlchemy
            Query object. The query should render a SELECT on the table on
            which access permissions are to be enforced, returning only rows
            that are accessible under the policy (See Example 1 below).

            In cases where the access control logic is different for
            different users, the class should be instantiated with a function
            that takes two arguments, cls (the mapped class corresponding to
            the table on which access permissions are to be enforced) and
            user_or_token, the instance of `baselayer.app.models.User` or
            `baselayer.app.models.Token` to check permissions for (See Example 2
            below). The function should then return a `sqlalchemy.orm.Query`
            object that, when executed, returns the rows accessible to that User
            or Token.

        Examples
        --------
        (1) Only permit access to departments in which all employees are
        managers

            >>>> CustomUserAccessControl(
                DBSession().query(Department).join(Employee).group_by(
                    Department.id
                ).having(sa.func.bool_and(Employee.is_manager.is_(True)))
            )

        (2) Permit access to all records for system admins, otherwise, only
        permit access to departments in which all employees are managers

             >>>> def access_logic(cls, user_or_token):
             ...      if user_or_token.is_system_admin:
             ...         return DBSession().query(cls)
             ...      return DBSession().query(cls).join(Employee).group_by(
             ...             cls.id
             ...      ).having(sa.func.bool_and(Employee.is_manager.is_(True)))

            >>>> CustomUserAccessControl(access_logic)

        """
        if isinstance(query_or_query_generator, sa.orm.Query):
            self.query = query_or_query_generator
            self.query_generator = None
        elif hasattr(query_or_query_generator, "__call__"):
            self.query = None
            self.query_generator = query_or_query_generator
        else:
            raise TypeError(
                f"Invalid type for query: "
                f"{type(query_or_query_generator).__name__}, "
                f"expected `sqlalchemy.orm.Query` or func."
            )

    def query_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Query object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls: `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns: list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        query: sqlalchemy.Query
            Query for the accessible rows.
        """

        if self.query is not None:
            query = self.query
        else:
            query = self.query_generator(cls, user_or_token)

        # retrieve specified columns if requested
        if columns is not None:
            query = query.with_entities(*columns)

        return query


class BaseMixin:

    # permission control logic
    create = read = public
    update = delete = restricted

    def is_accessible_by(self, user_or_token, mode="read"):
        """Check if a User or Token has a specified type of access to this
        database record.

        Parameters
        ----------
        user_or_token: `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        mode: string
            Type of access to check.
        Returns
        -------
        accessible: bool
            Whether the User or Token has the specified type of access to
            the record.
        """

        # get the classmethod that determines whether a record of type `cls` is
        # accessible to a user or token
        cls = type(self)
        logic = getattr(cls, mode)

        # Construct the join from which accessibility can be selected.
        accessibility_target = (sa.func.count("*") > 0).label(f"{mode}_ok")
        accessibility_table = logic.query_accessible_rows(
            cls, user_or_token, columns=[accessibility_target]
        ).filter(cls.id == self.id)

        # Query for the value of the access_func for this particular record and
        # return the result.
        result = accessibility_table.scalar()
        if result is None:
            result = False

        if not isinstance(result, bool):
            raise RuntimeError(
                f"Non-boolean result ({result}) from operation "
                f'"{type(user_or_token).__name__} {user_or_token.id} '
                f'{mode} {cls.__name__} {self.id}".'
            )

        return result

    @classmethod
    def get_if_accessible_by(
        cls,
        cls_id,
        user_or_token,
        mode="read",
        raise_if_none=False,
        options=[],
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

        # TODO: vectorize this
        for pk in standardized:
            instance = cls.query.options(options).get(pk.item())
            if instance is not None:
                if not instance.is_accessible_by(user_or_token, mode=mode):
                    raise AccessError(
                        f"Insufficient permissions for operation "
                        f'"{type(user_or_token).__name__} {user_or_token.id} '
                        f'{mode} {cls.__name__} {instance.id}".'
                    )
            elif raise_if_none:
                raise AccessError(f"Invalid {cls.__name__} id: {pk}")
            result.append(instance)
        return np.asarray(result).reshape(original_shape).tolist()

    @classmethod
    def get_records_accessible_by(
        cls, user_or_token, mode="read", options=[], columns=None
    ):
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
            user_or_token, mode=mode, options=options, columns=columns
        ).all()

    @classmethod
    def query_records_accessible_by(
        cls, user_or_token, mode="read", options=[], columns=None
    ):
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
                "user_or_token must be an instance of User or Token, "
                f"got {user_or_token.__class__.__name__}."
            )

        logic = getattr(cls, mode)
        return logic.query_accessible_rows(
            cls, user_or_token, columns=columns
        ).options(options)

    query = DBSession.query_property()
    id = sa.Column(
        sa.Integer,
        primary_key=True,
        autoincrement=True,
        doc="Unique object identifier.",
    )
    created_at = sa.Column(
        sa.DateTime,
        nullable=False,
        default=utcnow,
        index=True,
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
        return cls.__name__.lower() + "s"

    __mapper_args__ = {"confirm_deleted_rows": False}

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
            k: v for k, v in self.__dict__.items() if not k.startswith("_")
        }

    @classmethod
    def get_if_readable_by(cls, ident, user_or_token, options=[]):
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

        if obj is not None and not obj.is_readable_by(user_or_token):
            raise AccessError("Insufficient permissions.")

        return obj

    def is_readable_by(self, user_or_token):
        """Return a boolean indicating whether a User or Token has read access
        to this object.

        Parameters
        ----------
        user_or_token : `baselayer.app.models.User` or `baselayer.app.models.Token`
           The User or Token to check.

        Returns
        -------
        readable : bool
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


class JoinModel:
    """Dummy class that join_models subclass. Provides an easy way to
    access all join_model mapped classes via the __subclasses__() method.
    """

    pass


def join_model(
    join_table,
    model_1,
    model_2,
    column_1=None,
    column_2=None,
    fk_1="id",
    fk_2="id",
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
        column_1 = f"{table_1[:-1]}_id"
    if column_2 is None:
        column_2 = f"{table_2[:-1]}_id"

    forward_ind_name = f"{join_table}_forward_ind"
    reverse_ind_name = f"{join_table}_reverse_ind"

    model_attrs = {
        "__tablename__": join_table,
        "id": sa.Column(
            sa.Integer, primary_key=True, doc="Unique object identifier."
        ),
        column_1: sa.Column(
            column_1,
            sa.ForeignKey(f"{table_1}.{fk_1}", ondelete="CASCADE"),
            nullable=False,
        ),
        column_2: sa.Column(
            column_2,
            sa.ForeignKey(f"{table_2}.{fk_2}", ondelete="CASCADE"),
            nullable=False,
        ),
    }

    model_attrs.update(
        {
            model_1.__name__.lower(): relationship(
                model_1,
                cascade="save-update, merge, refresh-expire, expunge",
                foreign_keys=[model_attrs[column_1]],
            ),
            model_2.__name__.lower(): relationship(
                model_2,
                cascade="save-update, merge, refresh-expire, expunge",
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

    model = type(
        model_1.__name__ + model_2.__name__, (base, JoinModel), model_attrs
    )
    model.read = model.create = AccessibleIfRelatedRowsAreAccessible(
        **{model_1.__name__.lower(): "read", model_2.__name__.lower(): "read"}
    )
    return model


class ACL(Base):
    """An access control list item representing a privilege within the
    application. ACLs are aggregated into collections called Roles which
    are assumed by Users. Examples of ACLs include `Upload Data`, `Comment`,
    and `Manage Groups`.
    """

    id = sa.Column(
        sa.String, nullable=False, primary_key=True, doc="ACL name."
    )


class Role(Base):
    """A collection of ACLs. Roles map Users to ACLs. One User may assume
    multiple Roles."""

    id = sa.Column(
        sa.String, nullable=False, primary_key=True, doc="Role name."
    )
    acls = relationship(
        "ACL",
        secondary="role_acls",
        passive_deletes=True,
        doc="ACLs associated with the Role.",
    )
    users = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        passive_deletes=True,
        doc="Users who have this Role.",
    )


RoleACL = join_model("role_acls", Role, ACL)
RoleACL.__doc__ = "Join table class mapping Roles to ACLs."


def is_admin(self):
    return "System admin" in self.permissions


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
    oauth_uid = sa.Column(sa.String, unique=True, doc="The user's OAuth UID.")
    preferences = sa.Column(
        JSONB, nullable=True, doc="The user's application settings."
    )

    roles = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        passive_deletes=True,
        doc="The roles assumed by this user.",
    )
    role_ids = association_proxy(
        "roles",
        "id",
        creator=lambda r: Role.query.get(r),
    )
    tokens = relationship(
        "Token",
        cascade="save-update, merge, refresh-expire, expunge",
        back_populates="created_by",
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
    expiration_date = sa.Column(
        sa.DateTime,
        nullable=True,
        doc="The date until which the user's account is valid. Users are set to view-only upon expiration.",
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

        digest = md5(email.lower().encode("utf-8")).hexdigest()
        # return a transparent png if not found on gravatar
        return f"https://secure.gravatar.com/avatar/{digest}?d=blank"

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
        return (
            True
            if self.expiration_date is None
            else self.expiration_date > datetime.now()
        )

    is_admin = property(is_admin)


UserACL = join_model("user_acls", User, ACL)
UserACL.__doc__ = "Join table mapping Users to ACLs"


class Token(Base):
    """A command line token that can be used to programmatically access the API
    as a particular User."""

    create = read = update = delete = accessible_by_created_by

    id = sa.Column(
        sa.String,
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="The value of the token. This field is used for authenticating as "
        "a User on the command line.",
    )

    created_by_id = sa.Column(
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        doc="The ID of the User that created the Token.",
    )
    created_by = relationship(
        "User", back_populates="tokens", doc="The User that created the token."
    )
    acls = relationship(
        "ACL",
        secondary="token_acls",
        passive_deletes=True,
        doc="The ACLs granted to the Token.",
    )
    acl_ids = association_proxy(
        "acls", "id", creator=lambda acl: ACL.query.get(acl)
    )
    permissions = acl_ids

    name = sa.Column(
        sa.String,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
        doc="The name of the token.",
    )

    is_admin = property(is_admin)

    def is_readable_by(self, user_or_token):
        """Return a boolean indicating whether this Token is readable by the
        specified User (or Token instance, if a token is passed).

        Parameters
        ----------
        user_or_token : `baselayer.app.models.User` or `baselayer.app.models.Token`
           The User or Token to check.

        Returns
        -------
        readable : bool
           Whether this Token instance is readable by the User or Token.
        """
        return user_or_token.id in [self.created_by_id, self.id]

    __table_args__ = (sa.UniqueConstraint("created_by_id", "name", name="token_name_userid_unique_constraint"),)


TokenACL = join_model("token_acls", Token, ACL)
TokenACL.__doc__ = "Join table mapping Tokens to ACLs"
UserRole = join_model("user_roles", User, Role)
UserRole.__doc__ = "Join table mapping Users to Roles."


class CronJobRun(Base):
    """A record of a run (or attempted run) of a cron job."""

    script = sa.Column(
        sa.String,
        nullable=False,
        doc="Name of script being run.",
    )
    exit_status = sa.Column(
        sa.Integer,
        nullable=True,
        doc="Exit status of cron job subprocess (e.g. 0 or 1).",
    )
    output = sa.Column(
        sa.String,
        doc="Cron job's subprocess output, or exception string.",
    )
