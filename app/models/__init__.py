from .access import *
from .acl import ACL, Role
from .base import *
from .cron_job_run import CronJobRun
from .join import JoinModel, join_model
from .session import *
from .token import *
from .user import User
from .util import *

# Define these here to prevent circular imports elsewhere
RoleACL = join_model("role_acls", Role, ACL)
RoleACL.__doc__ = "Join table class mapping Roles to ACLs."

UserACL = join_model("user_acls", User, ACL)
UserACL.__doc__ = "Join table mapping Users to ACLs"
UserRole = join_model("user_roles", User, Role)
UserRole.__doc__ = "Join table mapping Users to Roles."

del access, acl, base, cron_job_run, join, session, token, user, util
