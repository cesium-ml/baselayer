__all__ = ['Base']

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.ext.declarative import declarative_base, declared_attr

import numpy as np

from .session import DBSession
from .access import public, restricted
from ..custom_exceptions import AccessError

from ..json_util import to_json


utcnow = func.timezone("UTC", func.current_timestamp())


class _BaseMixin:

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
        from .user import User
        from .token import Token
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


Base = declarative_base(cls=_BaseMixin)
