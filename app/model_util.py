import time

import sqlalchemy as sa

from baselayer.app import models

# Do not remove this "unused" import; psa initializes the Tornado models.
from . import psa  # noqa: F401


def drop_tables():
    conn = models.db_engine()
    print(f"Dropping tables on database {conn.url.database}")
    meta = sa.MetaData()
    meta.reflect(bind=conn)
    meta.drop_all(bind=conn)


def create_tables(retry=5, add=True):
    """Create tables for all models, retrying `retry` times at intervals of 3
    seconds if the database is not reachable.

    Parameters
    ----------
    retry : int
        Number of times to try creating the tables.
    add : bool
        Whether to add tables if some tables already exist.  This is
        convenient during development, but will cause problems
        for installations that depend on migrations to create new
        tables.

    """
    metadata = models.Base.metadata
    if not add and metadata.tables:
        print("Existing tables found; not creating additional tables")
        return

    for attempt in range(1, retry + 1):
        try:
            conn = models.db_engine()
            print(f"Creating tables on database {conn.url.database}")
            metadata.create_all(conn)
            print(f"Refreshed {len(metadata.tables)} tables")
            return
        except Exception as e:
            if attempt == retry:
                raise
            print(f"Could not connect to database (attempt {attempt}/{retry})")
            print(f"  > {e}")
            time.sleep(3)


def clear_tables():
    drop_tables()
    create_tables()


def recursive_to_dict(obj):
    if isinstance(obj, dict):
        return {k: recursive_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [recursive_to_dict(el) for el in obj]
    if hasattr(obj, "__table__"):
        return recursive_to_dict(obj.to_dict())
    return obj
