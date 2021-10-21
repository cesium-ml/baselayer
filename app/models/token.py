import uuid

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy.ext.associationproxy import association_proxy

from .base import Base
from .acl import ACL
from .join import join_model
from .access import accessible_by_created_by


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
        unique=True,
        default=lambda: str(uuid.uuid4()),
        doc="The name of the token.",
    )

    @property
    def is_admin(self):
        return "System admin" in self.permissions

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


TokenACL = join_model("token_acls", Token, ACL)
TokenACL.__doc__ = "Join table mapping Tokens to ACLs"
