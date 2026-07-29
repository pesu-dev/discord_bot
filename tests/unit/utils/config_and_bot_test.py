from __future__ import annotations

from types import SimpleNamespace
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
    guild.get_channel_or_thread = MagicMock(return_value=channel)
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
        assert bot.stores is not None
        assert bot.stores.links is not None
        assert bot.stores.mutes is not None


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


async def test_bot_load_cogs_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.logger = MagicMock()
    bot.load_extension = AsyncMock(side_effect=RuntimeError("fail"))
    with patch("src.bot.discover_cog_extensions", return_value=["src.cogs.bad"]):
        await bot.load_cogs()
    bot.logger.error.assert_called()


async def test_bot_status_and_before_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.change_presence = AsyncMock()
    bot.wait_until_ready = AsyncMock()
    await DiscordBot.status_task.coro(bot)
    bot.change_presence.assert_awaited()
    await DiscordBot.before_status_task(bot)
    bot.wait_until_ready.assert_awaited()


async def test_bot_setup_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.init_db = AsyncMock()
    bot.load_cogs = AsyncMock()
    bot.status_task.start = MagicMock()
    await bot.setup_hook()
    bot.init_db.assert_awaited()
    bot.load_cogs.assert_awaited()
    bot.status_task.start.assert_called_once()


async def test_bot_on_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.logger = MagicMock()
    type(bot).user = property(lambda self: SimpleNamespace(name="PESUBot", id=1))  # type: ignore[method-assign]
    logs = MagicMock()
    logs.send = AsyncMock()
    bot.config = MagicMock()
    bot.config.bot_logs_channel = logs
    await bot.on_ready()
    logs.send.assert_awaited_with("Bot is online")

    logs.send = AsyncMock(side_effect=RuntimeError("fail"))
    await bot.on_ready()
    bot.logger.error.assert_called()


async def test_bot_command_completion_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from discord.ext import commands

    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.logger = MagicMock()
    ctx = MagicMock(spec=commands.Context)
    ctx.command = None
    await bot.on_command_completion(ctx)

    ctx.command = MagicMock()
    ctx.command.qualified_name = "ping"
    ctx.author = MagicMock()
    ctx.author.id = 1
    ctx.guild = MagicMock()
    ctx.guild.name = "PESU"
    ctx.guild.id = 2
    await bot.on_command_completion(ctx)
    bot.logger.info.assert_called()

    ctx.guild = None
    await bot.on_command_completion(ctx)

    ctx.command.has_error_handler = MagicMock(return_value=True)
    await bot.on_command_error(ctx, commands.CommandError("x"))

    ctx.command.has_error_handler = MagicMock(return_value=False)
    ctx.cog = MagicMock()
    ctx.cog.has_error_handler = MagicMock(return_value=True)
    await bot.on_command_error(ctx, commands.CommandError("x"))

    ctx.cog.has_error_handler = MagicMock(return_value=False)
    ctx.send = AsyncMock()
    await bot.on_command_error(ctx, commands.CommandNotFound())

    param = MagicMock()
    param.name = "member"
    param.displayed_name = "member"
    param.kind = MagicMock()
    err = commands.MissingRequiredArgument(param)
    await bot.on_command_error(ctx, err)
    ctx.send.assert_awaited()

    await bot.on_command_error(ctx, commands.MissingPermissions(["kick_members"]))
    await bot.on_command_error(ctx, commands.BotMissingPermissions(["manage_messages"]))
    await bot.on_command_error(ctx, commands.CommandError("other"))
    bot.logger.error.assert_called()


def test_config_errors() -> None:
    bot = MagicMock()
    guild = MagicMock()
    guild.get_role = MagicMock(return_value=None)
    guild.get_channel_or_thread = MagicMock(return_value=None)
    bot.get_guild = MagicMock(return_value=guild)
    config = Config(bot, env="local", db_name="pesu_v2")
    with pytest.raises(ValueError, match="Role 'NOPE'"):
        config.get_role("NOPE")
    with pytest.raises(ValueError, match="Role with ID"):
        config.get_role("ADMIN")
    with pytest.raises(ValueError, match="Channel 'NOPE'"):
        config.get_channel("NOPE")
    with pytest.raises(ValueError, match="Channel with ID"):
        config.get_channel("BOT_LOGS")


def test_config_role_channel_properties() -> None:
    import discord

    bot = MagicMock()
    guild = MagicMock()
    role = MagicMock(spec=discord.Role)
    channel = MagicMock(spec=discord.TextChannel)
    guild.get_role = MagicMock(return_value=role)
    guild.get_channel_or_thread = MagicMock(return_value=channel)
    bot.get_guild = MagicMock(return_value=guild)
    config = Config(bot, env="local", db_name="pesu_v2")
    assert config.admin_role is role
    assert config.mod_role is role
    assert config.junior_mod_role is role
    assert config.bot_dev_role is role
    assert config.linked_role is role
    assert config.just_joined_role is role
    assert config.muted_role is role
    assert config.bot_logs_channel is channel
    assert config.mod_logs_channel is channel
    assert config.lobby_channel is channel
    assert config.verification_logs_channel is channel
    assert config.error_logs_channel is channel
    assert Config.PESU_AUTH_URL == "https://pesu-auth.onrender.com/authenticate"
    assert Config.CHANNELS["VERIFICATION_LOGS"] == 1100722146956820510
    assert Config.CHANNELS["ERROR_LOGS"] == 1129317221848596490
    assert "ADDITIONAL_ROLES" not in Config.CHANNELS


def test_branch_short_codes_from_portal() -> None:
    assert Config.BRANCH_SHORT_CODES["Civil Engineering"] == "CV"
    assert Config.BRANCH_SHORT_CODES["Master of Computer Applications"] == "MCA"
    assert "CE" not in Config.BRANCH_SHORT_CODES.values()


def test_resolve_academic_role_match() -> None:
    import discord

    bot = MagicMock()
    guild = MagicMock()
    role = MagicMock(spec=discord.Role)
    role.name = "CSE"
    role.color = MagicMock()
    role.color.value = Config.ACADEMIC_ROLE_COLOR
    guild.roles = [role]
    bot.get_guild = MagicMock(return_value=guild)
    config = Config(bot, env="local", db_name="pesu_v2")
    assert config.resolve_academic_role("CSE") is role


def test_resolve_academic_role_wrong_color() -> None:
    import discord

    bot = MagicMock()
    guild = MagicMock()
    role = MagicMock(spec=discord.Role)
    role.name = "CSE"
    role.color = MagicMock()
    role.color.value = 0xFF0000
    guild.roles = [role]
    bot.get_guild = MagicMock(return_value=guild)
    config = Config(bot, env="local", db_name="pesu_v2")
    with pytest.raises(ValueError, match="color"):
        config.resolve_academic_role("CSE")


def test_resolve_academic_role_missing() -> None:
    bot = MagicMock()
    guild = MagicMock()
    guild.roles = []
    bot.get_guild = MagicMock(return_value=guild)
    config = Config(bot, env="local", db_name="pesu_v2")
    with pytest.raises(ValueError, match="not found"):
        config.resolve_academic_role("NOPE")
