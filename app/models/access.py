__all__ = [
    'UserAccessControl',
    'Public',
    'AccessibleIfUserMatches',
    'AccessibleIfRelatedRowsAreAccessible',
    'ComposedAccessControl',
    'Restricted',
    'CustomUserAccessControl',
    'public',
    'restricted',
    'accessible_by_owner',
    'accessible_by_created_by',
    'accessible_by_user'
]

import sqlalchemy as sa

from .session import DBSession


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
        from .user import User
        from .token import Token
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
            target_alias = sa.orm.aliased(cls)

            # join against the first access control using a subquery. from a
            # performance perspective this should be about as performant as
            # aliasing the related table, but is much better for avoiding
            # name collisions. The subquery is automatically de-subbed by
            # postgres and uses all available indices.
            accessible = access_control.query_accessible_rows(
                target_alias, user_or_token, columns=[target_alias.id]
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


# Common access check instantiations
public = Public()
restricted = Restricted()
accessible_by_owner = AccessibleIfUserMatches("owner")
accessible_by_created_by = AccessibleIfUserMatches("created_by")
accessible_by_user = AccessibleIfUserMatches("user")
