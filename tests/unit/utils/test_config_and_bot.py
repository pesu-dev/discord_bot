from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.config import Config


def test_resolve_env_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    env, prefix, db = Config.resolve_env()
    assert env == "local"
    assert prefix == "?"
    assert db == "pesu_v2"


def test_resolve_env_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError, match="APP_ENV"):
        Config.resolve_env()


def test_config_guild_object() -> None:
    bot = MagicMock()
    config = Config(bot, env="local", db_name="pesu_v2")
    assert config.guild_object.id == Config.GUILD_ID


def test_config_get_role_and_channel() -> None:
    import discord

    bot = MagicMock()
    guild = MagicMock()
    role = MagicMock(spec=discord.Role)
    channel = MagicMock(spec=discord.TextChannel)
    guild.get_role = MagicMock(return_value=role)
    guild.get_channel = MagicMock(return_value=channel)
    bot.get_guild = MagicMock(return_value=guild)

    config = Config(bot, env="local", db_name="pesu_v2")
    assert config.admin_role is role
    assert config.bot_logs_channel is channel


def test_config_guild_missing() -> None:
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    config = Config(bot, env="local", db_name="pesu_v2")
    with pytest.raises(ValueError, match="Guild"):
        _ = config.guild


async def test_bot_init_db_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("MONGO_URI", "mongodb://example")

    fake_db = MagicMock()
    fake_db.__getitem__ = MagicMock(side_effect=lambda name: MagicMock(name=name))
    fake_client = MagicMock()
    fake_client.__getitem__ = MagicMock(return_value=fake_db)

    with patch("src.bot.AsyncMongoClient", return_value=fake_client):
        from src.bot import DiscordBot

        bot = DiscordBot()
        await bot.init_db()
        assert bot.link_collection is not None
        assert bot.mute_collection is not None


async def test_bot_init_db_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("MONGO_URI", raising=False)

    from src.bot import DiscordBot

    bot = DiscordBot()
    # Missing MONGO_URI raises KeyError caught by broad except
    await bot.init_db()


async def test_bot_load_cogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.load_extension = AsyncMock()
    with patch("src.bot.discover_cog_extensions", return_value=["src.cogs.eng"]):
        await bot.load_cogs()
    bot.load_extension.assert_awaited_with("src.cogs.eng")
