"""Integration fixtures: real MongoDB via Testcontainers + AsyncMongoClient."""

from __future__ import annotations

import os

import pytest
from pymongo import AsyncMongoClient
from testcontainers.mongodb import MongoDbContainer


@pytest.fixture(scope="session")
def mongo_url() -> str:
    # Ryuk's docker.sock remount breaks under some local setups (e.g. Colima).
    # GitHub Actions cleans up the runner anyway; disable Ryuk for portability.
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
    with MongoDbContainer("mongo:7") as mongo:
        yield mongo.get_connection_url()


@pytest.fixture
async def mongo_db(mongo_url: str):
    client = AsyncMongoClient(mongo_url, tz_aware=True)
    db = client["pesu_test"]
    yield db
    for name in await db.list_collection_names():
        await db[name].delete_many({})
    await client.close()


@pytest.fixture
async def wired_bot(mongo_db, fake_config, mock_bot):
    """mock_bot wired to real async collections from Testcontainers."""
    mock_bot.config = fake_config
    mock_bot.config.db_name = "pesu_test"
    mock_bot.link_collection = mongo_db["link"]
    mock_bot.student_collection = mongo_db["student"]
    mock_bot.anonban_collection = mongo_db["anonban"]
    mock_bot.mute_collection = mongo_db["mute"]
    mock_bot.anon_cache = {}
    return mock_bot
