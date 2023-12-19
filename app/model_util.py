import time
from contextlib import contextmanager

import sqlalchemy as sa

from baselayer.app import models

# Do not remove this "unused" import; it is required for
# psa to initialize the Tornado models
from . import psa  # noqa: F401


@contextmanager
def status(message):
    print(f"[·] {message}", end="")
    try:
        yield
    except:  # noqa: E722
        print(f"\r[✗] {message}")
        raise
    else:
        print(f"\r[✓] {message}")
    finally:
        models.HandlerSession().commit()


def drop_tables():
    engine = models.HandlerSession.engine
    print(f"Dropping tables on database {engine.url.database}")
    meta = sa.MetaData()
    meta.reflect(bind=engine)
    meta.drop_all(bind=engine)


def create_tables(retry=5, add=True):
    """Create tables for all models, retrying 5 times at intervals of 3
    seconds if the database is not reachable.

    Parameters
    ----------
    add : bool
        Whether to add tables if some tables already exist.  This is
        convenient during development, but will cause problems
        for installations that depend on migrations to create new
        tables.

    """
    tables = models.Base.metadata.sorted_tables
    if tables and not add:
        print("Existing tables found; not creating additional tables")
        return

    for i in range(1, retry + 1):
        try:
            engine = models.HandlerSession.engine
            print(f"Creating tables on database {engine.url.database}")
            models.Base.metadata.create_all(engine)

            table_list = ", ".join(list(models.Base.metadata.tables.keys()))
            print(f"Refreshed tables: {table_list}")
            # for m in models.Base.metadata.tables:
            #     print(f" - {m}")

            return

        except Exception as e:
            if i == retry:
                raise e
            else:
                print("Could not connect to database...sleeping 3")
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
    if hasattr(obj, "__table__"):  # SQLAlchemy model
        return recursive_to_dict(obj.to_dict())
    return obj
