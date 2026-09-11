"""Tests for `AsyncSession.upsert`, against the configured database.

Run from the directory holding `baselayer`, e.g.
``pytest baselayer/test --config=test_config.yaml``.
"""

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import declarative_base

from baselayer.app import models
from baselayer.app.models import cfg, init_db

Base = declarative_base()


class Widget(Base):
    __tablename__ = "baselayer_test_widget"

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String, unique=True, nullable=False)
    value = sa.Column(sa.Integer)


@pytest.fixture
def run_scenario():
    """Run ``scenario(session_factory)`` over a table of its own, on one event loop."""
    database = cfg["database"]["database"]
    if not str(database).endswith("_test"):
        pytest.fail(
            f"Refusing to create tables in {database!r}; "
            "run with --config=test_config.yaml"
        )

    def run(scenario):
        async def main():
            engine = init_db(**cfg["database"])
            try:
                async with models.async_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                    await conn.run_sync(Base.metadata.create_all)
                return await scenario(models.async_plain_session_factory)
            finally:
                async with models.async_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
                await models.async_engine.dispose()
                engine.dispose()

        return asyncio.run(main())

    return run


def test_upsert_updates_the_row_it_already_inserted(run_scenario):
    """Upserting twice on the same key keeps one row, carrying the new values."""

    async def scenario(session_factory):
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

    first_id, stored = run_scenario(scenario)

    assert stored == [(first_id, 2)]


def test_upsert_without_values_leaves_an_existing_row_alone(run_scenario):
    """A `by`-only upsert is a get-or-create; it does not blank the other columns."""

    async def scenario(session_factory):
        async with session_factory() as session:
            await session.upsert(Widget, by={"name": "widget"}, values={"value": 7})
            await session.commit()

            await session.upsert(Widget, by={"name": "widget"})
            await session.commit()

        async with session_factory() as session:
            return await session.scalar(
                sa.select(Widget.value).where(Widget.name == "widget")
            )

    assert run_scenario(scenario) == 7


def test_upsert_finds_its_pending_row_without_autoflush(run_scenario):
    """The app runs its session with autoflush off; upserting twice still adds one row."""

    async def scenario(session_factory):
        async with session_factory(autoflush=False) as session:
            first = await session.upsert(Widget, by={"name": "widget"})
            second = await session.upsert(Widget, by={"name": "widget"})
            await session.commit()

            rows = await session.scalar(sa.select(sa.func.count()).select_from(Widget))
            return first is second, rows

    same, rows = run_scenario(scenario)

    assert same
    assert rows == 1


def test_upsert_refuses_values_that_contradict_the_key(run_scenario):
    """`values` may repeat what `by` says, but not rename the row out of its key."""

    async def scenario(session_factory):
        async with session_factory() as session:
            with pytest.raises(ValueError):
                await session.upsert(Widget, by={"name": "old"}, values={"name": "new"})

            await session.upsert(Widget, by={"name": "old"}, values={"name": "old"})
            await session.commit()

        async with session_factory() as session:
            return (await session.scalars(sa.select(Widget.name))).all()

    assert run_scenario(scenario) == ["old"]


def test_upsert_refuses_a_key_matching_several_rows(run_scenario):
    """A `by` that is not unique is an error, not an arbitrary choice of row."""

    async def scenario(session_factory):
        async with session_factory(autoflush=False) as session:
            session.add_all([Widget(name="a", value=1), Widget(name="b", value=1)])

            with pytest.raises(MultipleResultsFound):
                await session.upsert(Widget, by={"value": 1}, values={"name": "c"})

            await session.commit()

            with pytest.raises(MultipleResultsFound):
                await session.upsert(Widget, by={"value": 1}, values={"name": "c"})

    run_scenario(scenario)


def test_upsert_refuses_an_empty_key(run_scenario):
    """An empty `by` would match every row, so it is an error."""

    async def scenario(session_factory):
        async with session_factory() as session:
            await session.upsert(Widget, by={}, values={"value": 1})

    with pytest.raises(ValueError):
        run_scenario(scenario)


def test_the_verified_session_looks_up_only_accessible_rows(run_scenario, monkeypatch):
    """The verified session looks the row up through `model.select`, so a row the
    accessor cannot read is not found and a new one is added instead."""

    monkeypatch.setattr(
        Widget,
        "select",
        staticmethod(lambda user_or_token: sa.select(Widget).where(sa.false())),
        raising=False,
    )

    async def scenario(session_factory):
        async with session_factory() as session:
            await session.upsert(Widget, by={"name": "widget"}, values={"value": 1})
            await session.commit()

        verified = models.async_session_factory()
        verified.user_or_token = "user"
        async with verified:
            found = await verified.upsert(Widget, by={"name": "widget"})
            found_id = found.id
            await verified.rollback()
        return found_id

    assert run_scenario(scenario) is None
