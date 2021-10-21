__all__ = ['JoinModel', 'join_model']

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from .base import Base
from .access import AccessibleIfRelatedRowsAreAccessible


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
