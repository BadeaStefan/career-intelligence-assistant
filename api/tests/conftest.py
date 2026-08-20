"""Shared test fixtures.

Tests run against a real Postgres, not SQLite. pgvector's ``vector`` type has
no SQLite equivalent, so a substituted backend would silently skip exactly the
behaviour this suite exists to verify.

Isolation is by truncation rather than by wrapping each test in a transaction
that gets rolled back. Background enrichment deliberately opens its *own*
session so it can outlive the request that scheduled it, and work committed
there cannot be undone by rolling back some other transaction. Truncation
isolates every path uniformly.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

API_ROOT = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/career_intel_test",
)


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> Iterator[None]:
    """Point the application at the test database and bring it to head.

    The environment is set before any application module reads settings, so
    code that opens its own session -- background tasks especially -- lands in
    the test database rather than the development one.

    Schema is built by applying the real migrations, not
    ``metadata.create_all``. Models and migrations can drift apart unnoticed
    until a deploy fails; building from migrations makes drift break the suite.
    """
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    from career_intel import db
    from career_intel.config import get_settings

    get_settings.cache_clear()
    db.reset_engine()

    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    yield

    get_settings.cache_clear()
    db.reset_engine()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    yield

    from career_intel.models import Base

    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)

    # NullPool: this engine exists for one statement, and a pooled connection
    # outliving it would be reused from whichever event loop happens to run the
    # next test.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session against the test database. Commits are real."""
    from career_intel.db import get_session_factory

    async with get_session_factory()() as db_session:
        yield db_session


@pytest.fixture
def session_factory():
    """The same session factory production code uses to write telemetry.

    Exposed directly (rather than only via the ``session`` fixture) because
    telemetry writes must each open and commit their own session -- tests
    that assert on committed rows need to open a *fresh* one afterwards.
    """
    from career_intel.db import get_session_factory

    return get_session_factory()


@pytest.fixture
def settings():
    from career_intel.config import get_settings

    return get_settings()


@pytest.fixture
def openai_stub():
    from tests.fixtures.openai_stub import FakeOpenAIRaw

    return FakeOpenAIRaw()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient against the test database.

    Entering the context manager runs the application lifespan, so these tests
    also exercise the startup sweep.

    The engine is reset on both sides. TestClient runs the application in its
    own thread with its own event loop, and asyncpg binds connections to the
    loop that opened them -- so the app must build its engine inside that loop,
    and the pytest-side code that runs afterwards must not inherit it.
    """
    from career_intel import db
    from career_intel.api.app import create_app

    db.reset_engine()

    with TestClient(create_app()) as test_client:
        yield test_client

    db.reset_engine()
