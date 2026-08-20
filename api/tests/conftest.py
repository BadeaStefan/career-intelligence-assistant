"""Shared test fixtures.

Tests run against a real Postgres, not SQLite. pgvector's ``vector`` type has
no SQLite equivalent, so a substituted backend would silently skip exactly the
behaviour this suite exists to verify.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

API_ROOT = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/career_intel_test",
)


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    """Bring the test database to head via the real migrations.

    Deliberately not ``Base.metadata.create_all()``. Models and migrations can
    drift apart without anyone noticing until a deploy fails; building the test
    schema from the migrations means any drift breaks the suite instead.
    """
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """An AsyncSession wrapped in a transaction that is always rolled back.

    Each test therefore sees a clean database without paying to recreate the
    schema between tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.connect() as connection:
        transaction = await connection.begin()
        maker = async_sessionmaker(bind=connection, expire_on_commit=False)

        async with maker() as db_session:
            yield db_session

        await transaction.rollback()

    await engine.dispose()
