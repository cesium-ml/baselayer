__all__ = ['DBSession']

import contextvars
from sqlalchemy.orm import scoped_session, sessionmaker

session_context_id = contextvars.ContextVar("request_id", default=None)
DBSession = scoped_session(sessionmaker(), scopefunc=session_context_id.get)
