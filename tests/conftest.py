"""Shared pytest fixtures for unit and integration tests."""

from __future__ import annotations

import os
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.data.mongo import Link, Student

# Ensure Config.resolve_env / bot init never require a real .env during tests.
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
os.environ.setdefault("ASKPESU_API", "https://askpesu.test/api")

type RoleFactory = Callable[..., MagicMock]
type MemberFactory = Callable[..., MagicMock]
type InteractionFactory = Callable[..., MagicMock]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark tests by directory so CI can split unit vs integration."""
    for item in items:
        raw = getattr(item, "path", None) or getattr(item, "fspath", None)
        path = str(raw).replace("\\", "/") if raw is not None else ""
        if "/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/unit/" in path:
            item.add_marker(pytest.mark.unit)
        else:
            # Default root-level tests (if any) to unit.
            item.add_marker(pytest.mark.unit)


def make_role(*, role_id: int, name: str = "role") -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    role.__eq__ = lambda self, other: getattr(other, "id", None) == role_id  # type: ignore[method-assign]
    role.__hash__ = lambda self: hash(role_id)  # type: ignore[method-assign]
    return role


def make_member(
    *,
    user_id: int = 1001,
    roles: list[MagicMock] | None = None,
    bot: bool = False,
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = bot
    member.roles = list(roles or [])
    member.mention = f"<@{user_id}>"
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://cdn.example/avatar.png"
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    member.kick = AsyncMock()
    member.send = AsyncMock()
    member.timeout = AsyncMock()
    member.is_timed_out = MagicMock(return_value=False)
    return member


def make_text_channel(*, channel_id: int = 2001, guild: MagicMock | None = None) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.guild = guild if guild is not None else MagicMock(spec=discord.Guild)
    channel.mention = f"<#{channel_id}>"
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()
    channel.permissions_for = MagicMock(return_value=SimpleNamespace(send_messages=True))
    # Satisfy decorators._is_guild_messageable isinstance checks via duck typing:
    # MagicMock is not a real TextChannel, so tests patch location checks or use
    # Interaction with channel that passes our helper mocks.
    return channel


def make_interaction(
    *,
    user: MagicMock | None = None,
    channel: MagicMock | None = None,
    guild: MagicMock | None = None,
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = user or make_member()
    interaction.guild = guild
    if guild is None and channel is not None:
        interaction.guild = getattr(channel, "guild", None)
    interaction.channel = channel or make_text_channel(guild=interaction.guild)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.fixture
def role_factory() -> RoleFactory:
    return make_role


@pytest.fixture
def member_factory() -> MemberFactory:
    return make_member


@pytest.fixture
def interaction_factory() -> InteractionFactory:
    return make_interaction


@pytest.fixture
def functional_roles() -> dict[str, MagicMock]:
    from src.utils.config import Config

    return {name: make_role(role_id=role_id, name=name) for name, role_id in Config.ROLES["FUNCTIONAL"].items()}


@pytest.fixture
def fake_config(functional_roles: dict[str, MagicMock]) -> MagicMock:
    """Config stand-in with role/channel attributes used by decorators and cogs."""
    from src.utils.config import Config

    config = MagicMock()
    config.guild_id = Config.GUILD_ID
    config.env = "local"
    config.db_name = "pesu_v2_test"
    config.guild_object = discord.Object(id=Config.GUILD_ID)

    config.admin_role = functional_roles["ADMIN"]
    config.mod_role = functional_roles["MOD"]
    config.bot_dev_role = functional_roles["BOT_DEV"]
    config.linked_role = functional_roles["LINKED"]
    config.just_joined_role = functional_roles["JUST_JOINED"]
    config.muted_role = functional_roles["MUTED"]

    year_roles = {name: make_role(role_id=role_id, name=name) for name, role_id in Config.ROLES["YEAR"].items()}
    branch_roles = {name: make_role(role_id=role_id, name=name) for name, role_id in Config.ROLES["BRANCH"].items()}
    campus_roles = {name: make_role(role_id=role_id, name=name) for name, role_id in Config.ROLES["CAMPUS"].items()}

    def get_role(category: str, name: str) -> MagicMock:
        mapping = {
            "FUNCTIONAL": functional_roles,
            "YEAR": year_roles,
            "BRANCH": branch_roles,
            "CAMPUS": campus_roles,
        }
        role = mapping.get(category, {}).get(name)
        if role is None:
            raise ValueError(f"Role '{name}' not found in category '{category}'")
        return role

    config.get_role = get_role
    config.bot_logs_channel = make_text_channel(channel_id=Config.CHANNELS["BOT_LOGS"])
    config.mod_logs_channel = make_text_channel(channel_id=Config.CHANNELS["MOD_LOGS"])
    config.lobby_channel = make_text_channel(channel_id=Config.CHANNELS["LOBBY"])
    return config


@pytest.fixture
def mock_bot(fake_config: MagicMock) -> MagicMock:
    bot = MagicMock()
    bot.config = fake_config
    bot.latency = 0.042
    bot.start_time = 1_700_000_000.0
    bot.logger = MagicMock()
    bot.anon_cache = {}
    stores = MagicMock()
    stores.links = AsyncMock()
    stores.students = AsyncMock()
    stores.anonbans = AsyncMock()
    stores.mutes = AsyncMock()
    bot.stores = stores
    bot.wait_until_ready = AsyncMock()
    bot.load_extension = AsyncMock()
    bot.unload_extension = AsyncMock()
    bot.reload_extension = AsyncMock()
    return bot


@pytest.fixture
def sample_student_doc() -> dict[str, Any]:
    return {
        "prn": "PES1UG21CS001",
        "year": "2021",
        "branch": {"full": "Computer Science and Engineering", "short": "CSE"},
        "campus": {"code": 1, "short": "RR"},
    }


@pytest.fixture
def sample_link_doc() -> dict[str, Any]:
    from bson import ObjectId

    return {
        "_id": ObjectId(),
        "userId": "1001",
        "prn": "PES1UG21CS001",
        "linkedAt": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_link(sample_link_doc: dict[str, Any]) -> Link:
    return Link.from_document(sample_link_doc)


@pytest.fixture
def sample_student(sample_student_doc: dict[str, Any]) -> Student:
    return Student.from_document(sample_student_doc)
