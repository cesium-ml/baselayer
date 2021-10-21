__all__ = ['User']

from hashlib import md5
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy_utils import EmailType, PhoneNumberType
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy

from slugify import slugify

from .base import Base
from .acl import Role


class _SlugifiedStr(sa.types.TypeDecorator):
    """Slugified string"""

    impl = sa.String

    # Used with INSERT
    def process_bind_param(self, value, dialect):
        return slugify(value)

    # Used with SELECT
    def process_result_value(self, value, dialect):
        return value


class User(Base):
    """An application user."""

    username = sa.Column(
        _SlugifiedStr, nullable=False, unique=True, doc="The user's username."
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

    @property
    def is_admin(self):
        return "System admin" in self.permissions

# See __init__.py for definition of UserACL, UserRole
