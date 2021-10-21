__all__ = ['ACL', 'Role']

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from .base import Base


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

# See __init__.py for definition of RoleACL
