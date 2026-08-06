"""Integration fixtures: real MongoDB via Testcontainers + AsyncMongoClient."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from pymongo import AsyncMongoClient
from testcontainers.mongodb import MongoDbContainer

from src.data.mongo import Stores

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from unittest.mock import MagicMock

    from pymongo.asynchronous.database import AsyncDatabase


@pytest.fixture(scope="session")
def mongo_url() -> Iterator[str]:
    # Ryuk's docker.sock remount breaks under some local setups (e.g. Colima).
    # GitHub Actions cleans up the runner anyway; disable Ryuk for portability.
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
    with MongoDbContainer("mongo:7") as mongo:
        yield mongo.get_connection_url()


@pytest.fixture
async def mongo_db(mongo_url: str) -> AsyncIterator[AsyncDatabase]:
    client = AsyncMongoClient(mongo_url, tz_aware=True)
    db = client["pesu_test"]
    yield db
    for name in await db.list_collection_names():
        await db[name].delete_many({})
    await client.close()


@pytest.fixture
async def wired_bot(
    mongo_db: AsyncDatabase,
    fake_config: MagicMock,
    mock_bot: MagicMock,
) -> AsyncIterator[MagicMock]:
    """mock_bot wired to real typed stores from Testcontainers Mongo."""
    mock_bot.config = fake_config
    mock_bot.config.db_name = "pesu_test"
    mock_bot.stores = Stores(mongo_db)
    mock_bot.anon_cache = {}
    yield mock_bot
