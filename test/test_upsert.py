"""Tests for `AsyncSession.upsert`, against the configured database.

Run from the directory holding `baselayer`, e.g.
``pytest baselayer/test --config=test_config.yaml``.
"""

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from baselayer.app.models import _AsyncPlainSession, cfg

Base = declarative_base()


class Widget(Base):
    __tablename__ = "baselayer_test_widget"

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String, unique=True, nullable=False)
    value = sa.Column(sa.Integer)


def database_url():
    db = cfg["database"]
    return "postgresql+psycopg://{}:{}@{}:{}/{}".format(
        db["user"],
        db.get("password") or "",
        db.get("host") or "",
        db.get("port") or "",
        db["database"],
    )


@pytest.fixture
def session_factory():
    """A plain async session factory over a table created for the test."""

    async def setup():
        engine = create_async_engine(database_url())
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        return engine

    async def teardown(engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    engine = asyncio.run(setup())
    yield async_sessionmaker(
        bind=engine, class_=_AsyncPlainSession, expire_on_commit=False
    )
    asyncio.run(teardown(engine))


def test_upsert_updates_the_row_it_already_inserted(session_factory):
    """Upserting twice on the same key keeps one row, carrying the new values."""

    async def scenario():
        async with session_factory() as session:
            first = await session.upsert(
                Widget, by={"name": "widget"}, values={"value": 1}
            )
            await session.commit()
            first_id = first.id

            await session.upsert(Widget, by={"name": "widget"}, values={"value": 2})
            await session.commit()

        async with session_factory() as session:
            stored = (await session.execute(sa.select(Widget.id, Widget.value))).all()
            return first_id, stored

    first_id, stored = asyncio.run(scenario())

    assert stored == [(first_id, 2)]


def test_upsert_leaves_an_implicit_key_to_the_database(session_factory):
    """`by` holds a natural key, so the database still assigns the surrogate id."""

    async def scenario():
        async with session_factory() as session:
            first = await session.upsert(Widget, by={"name": "one"})
            second = await session.upsert(Widget, by={"name": "two"})
            await session.commit()
            return first.id, second.id

    first_id, second_id = asyncio.run(scenario())

    assert first_id is not None and second_id is not None
    assert first_id != second_id


def test_upsert_without_values_leaves_an_existing_row_alone(session_factory):
    """A `by`-only upsert is a get-or-create; it does not blank the other columns."""

    async def scenario():
        async with session_factory() as session:
            await session.upsert(Widget, by={"name": "widget"}, values={"value": 7})
            await session.commit()

            await session.upsert(Widget, by={"name": "widget"})
            await session.commit()

        async with session_factory() as session:
            return await session.scalar(
                sa.select(Widget.value).where(Widget.name == "widget")
            )

    assert asyncio.run(scenario()) == 7


def test_upsert_twice_in_one_session_touches_one_row(session_factory):
    """The pending insert is flushed before the second lookup, so it is found."""

    async def scenario():
        async with session_factory() as session:
            first = await session.upsert(Widget, by={"name": "widget"})
            second = await session.upsert(Widget, by={"name": "widget"})
            await session.commit()

            rows = await session.scalar(sa.select(sa.func.count()).select_from(Widget))
            return first is second, rows

    same, rows = asyncio.run(scenario())

    assert same
    assert rows == 1


def test_upsert_refuses_a_key_matching_several_rows(session_factory):
    """A `by` that is not unique is an error, not an arbitrary choice of row."""

    async def scenario():
        async with session_factory() as session:
            session.add_all([Widget(name="a", value=1), Widget(name="b", value=1)])
            await session.commit()
            await session.upsert(Widget, by={"value": 1}, values={"value": 2})

    with pytest.raises(MultipleResultsFound):
        asyncio.run(scenario())


def test_upsert_refuses_an_empty_key(session_factory):
    """An empty `by` would match every row, so it is an error."""

    async def scenario():
        async with session_factory() as session:
            await session.upsert(Widget, by={}, values={"value": 1})

    with pytest.raises(ValueError):
        asyncio.run(scenario())


def test_upsert_inserts_a_row_its_own_key_finds_again(session_factory):
    """`by` wins over `values`, so a second identical call finds the first row."""

    async def scenario():
        async with session_factory() as session:
            await session.upsert(Widget, by={"name": "old"}, values={"name": "new"})
            await session.commit()

            await session.upsert(Widget, by={"name": "old"}, values={"name": "new"})
            await session.commit()

            return await session.scalar(sa.select(sa.func.count()).select_from(Widget))

    assert asyncio.run(scenario()) == 1


def test_upsert_finds_its_pending_row_without_autoflush(session_factory):
    """The app runs the session with autoflush off; upserting twice still adds one row."""

    async def scenario():
        async with session_factory(autoflush=False) as session:
            first = await session.upsert(Widget, by={"name": "widget"})
            second = await session.upsert(Widget, by={"name": "widget"})
            await session.commit()

            rows = await session.scalar(sa.select(sa.func.count()).select_from(Widget))
            return first is second, rows

    same, rows = asyncio.run(scenario())

    assert same
    assert rows == 1
