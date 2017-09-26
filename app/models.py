from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.orm.exc import NoResultFound

from .json_util import to_json
from .custom_exceptions import AccessError


DBSession = scoped_session(sessionmaker())


# The db has to be initialized later; this is done by the app itself
# See `app_server.py`
def init_db(user, database, password=None, host=None, port=None):
    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(user, password or '', host or '', port or '', database)

    conn = sa.create_engine(url, client_encoding='utf8')

    DBSession.configure(bind=conn)
    Base.metadata.bind = conn

    return conn


class BaseMixin(object):
    query = DBSession.query_property()
    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(sa.DateTime, nullable=False, default=datetime.now)

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower() + 's'

    __mapper_args__ = {'confirm_deleted_rows': False}

    def __str__(self):
        return to_json(self)

    def __repr__(self):
        attr_list = [f"{c.name}={getattr(self, c.name)}"
                     for c in self.__table__.columns]
        return f"<{type(self).__name__}({', '.join(attr_list)})>"

    def to_dict(self):
        if sa.inspection.inspect(self).expired:
            DBSession().refresh(self)
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    @classmethod
    def get_if_owned_by(cls, ident, user, options=[]):
        obj = cls.query.options(options).get(ident)

        if obj is None or not obj.is_owned_by(user):
            raise AccessError(f'No such {cls.__name__}')

        return obj

    def is_owned_by(self, user):
        raise NotImplementedError("Ownership logic is application-specific")


Base = declarative_base(cls=BaseMixin)


def join_model(join_table, model_1, model_2, column_1=None, column_2=None,
               fk_1='id', fk_2='id', base=Base):
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

    model_attrs = {
        '__tablename__': join_table,
        'id': None,
        column_1: sa.Column(column_1, sa.ForeignKey(f'{table_1}.{fk_1}',
                                                    ondelete='CASCADE'),
                            primary_key=True),
        column_2: sa.Column(column_2, sa.ForeignKey(f'{table_2}.{fk_2}',
                                                    ondelete='CASCADE'),
                            primary_key=True),
        model_1.__name__.lower(): relationship(model_1, cascade='all'),
        model_2.__name__.lower(): relationship(model_2, cascade='all')
    }
    model = type(model_1.__name__ + model_2.__name__, (base,), model_attrs)

    return model


class ACL(Base):
    id = sa.Column(sa.String, nullable=False, primary_key=True)
    roles = relationship('Role', secondary='role_acls', back_populates='acls',
                         cascade='all')


class Role(Base):
    id = sa.Column(sa.String, nullable=False, primary_key=True)
    acls = relationship('ACL', secondary='role_acls', back_populates='roles',
                        cascade='all')
    users = relationship('User', secondary='user_roles', back_populates='roles',
                         cascade='all')


RoleACL = join_model('role_acls', Role, ACL)


class User(Base):
    username = sa.Column(sa.String, nullable=False, unique=True)
    roles = relationship('Role', secondary='user_roles', back_populates='users',
                         cascade='all')
    role_ids = association_proxy('roles', 'id', creator=lambda r: Role.query.get(r))
    acls = relationship(ACL, secondary='join(roles, user_roles).'
                                       'join(role_acls)',
                        primaryjoin='user_roles.c.user_id == users.c.id')
    permissions = association_proxy('acls', 'id')

    @classmethod
    def user_model(cls):
        return User

    def is_authenticated(self):
        return True

    def is_active(self):
        return True


UserRole = join_model('user_roles', User, Role)
