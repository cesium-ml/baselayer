__all__ = ['init_db']

import sqlalchemy as sa

from .base import Base, DBSession

# https://docs.sqlalchemy.org/en/13/dialects/postgresql.html#psycopg2-fast-execution-helpers
# executemany_values_page_size arguments control how many parameter sets
# should be represented in each execution of an INSERT
# 50000 was chosen based on recommendations in the docs and on profiling tests
EXECUTEMANY_PAGESIZE = 50000


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
