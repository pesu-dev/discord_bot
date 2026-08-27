from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.cogs.eng.mongo import EngMongoCommands
from src.utils.atlas import AtlasAPIError, AtlasDatabaseUser
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


def _cmd(mock_bot: MagicMock) -> EngMongoCommands:
    commands = EngMongoCommands()
    commands.client = mock_bot
    return commands


async def test_access_unconfigured(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = _cmd(mock_bot)
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=None):
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member_factory(), "discord_ro", 2)
    assert "not configured" in interaction.followup.send.await_args.kwargs["content"]


async def test_access_grant(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = _cmd(mock_bot)
    interaction = interaction_factory()
    member = member_factory(user_id=10)
    member.name = "bob"
    atlas = MagicMock()
    atlas.create_or_update_temp_user = AsyncMock(return_value="Granted")
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas) as from_config:
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member, "discord_ro", 8)
    from_config.assert_called_once_with(mock_bot.config, "dev")
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Granted" in content
    assert "discord_ro" in content
    assert "<t:" in content
    assert "`dev`" in content


async def test_access_rejects_disallowed_role(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = _cmd(mock_bot)
    interaction = interaction_factory()
    member = member_factory()
    atlas = MagicMock()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member, "atlasAdmin", 2)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Role must be one of" in content
    assert "`discord_ro`" in content
    assert "`discord_rw`" in content
    atlas.create_or_update_temp_user.assert_not_called()


async def test_access_update_and_atlas_error(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = _cmd(mock_bot)
    interaction = interaction_factory()
    member = member_factory()
    atlas = MagicMock()
    atlas.create_or_update_temp_user = AsyncMock(return_value="Updated")
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member, "discord_rw", 1)
    assert "Updated" in interaction.followup.send.await_args.kwargs["content"]

    atlas.create_or_update_temp_user = AsyncMock(
        side_effect=AtlasAPIError(httpx.Response(400, json={"detail": "bad role"}))
    )
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member, "discord_ro", 1)
    assert "400" in interaction.followup.send.await_args.kwargs["content"]

    atlas.create_or_update_temp_user = AsyncMock(side_effect=ValueError("duration must be between 1 and 8 hours"))
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member, "discord_ro", 1)
    assert "duration" in interaction.followup.send.await_args.kwargs["content"]

    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_access)(cmd, interaction, "dev", member, "discord_ro", 9)
    assert "between 1 and 8" in interaction.followup.send.await_args.kwargs["content"]


async def test_access_role_autocomplete(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = _cmd(mock_bot)
    interaction = interaction_factory()
    interaction.namespace = SimpleNamespace(environment=None)
    empty = await cmd.eng_mongo_access_role_autocomplete(interaction, "")
    assert empty[0].value == ""

    interaction.namespace = SimpleNamespace(environment="dev")
    roles = await cmd.eng_mongo_access_role_autocomplete(interaction, "rw")
    assert [choice.value for choice in roles] == ["discord_rw"]


async def test_list_paths(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = _cmd(mock_bot)
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=None):
        await get_callback(cmd.eng_mongo_list)(cmd, interaction, "dev")
    assert "not configured" in interaction.followup.send.await_args.kwargs["content"]

    atlas = MagicMock()
    atlas.list_eng_mongo_users = AsyncMock(side_effect=AtlasAPIError(httpx.Response(401, json={"detail": "nope"})))
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_list)(cmd, interaction, "dev")
    assert "401" in interaction.followup.send.await_args.kwargs["content"]

    atlas.list_eng_mongo_users = AsyncMock(return_value=[])
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_list)(cmd, interaction, "dev")
    assert "No temporary" in interaction.followup.send.await_args.kwargs["content"]

    atlas.list_eng_mongo_users = AsyncMock(
        return_value=[
            AtlasDatabaseUser(
                username="CN=10",
                discord_user_id=10,
                description='{"by":"99"}',
                labels={"expires": "1787043600"},
                role="discord_ro",
            ),
        ]
    )
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_list)(cmd, interaction, "dev")
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "discord_ro" in content
    assert "<@10>" in content
    assert "<@99>" in content
    assert "`dev`" in content


async def test_revoke_paths(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = _cmd(mock_bot)
    member = member_factory(user_id=10)
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=None):
        await get_callback(cmd.eng_mongo_revoke)(cmd, interaction, "dev", member)
    assert "not configured" in interaction.followup.send.await_args.kwargs["content"]

    atlas = MagicMock()
    atlas.delete_eng_users_for_discord_id = AsyncMock(
        side_effect=AtlasAPIError(httpx.Response(500, json={"detail": "boom"}))
    )
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_revoke)(cmd, interaction, "dev", member)
    assert "500" in interaction.followup.send.await_args.kwargs["content"]

    atlas.delete_eng_users_for_discord_id = AsyncMock(return_value=[])
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_revoke)(cmd, interaction, "dev", member)
    assert "No temporary grant" in interaction.followup.send.await_args.kwargs["content"]

    atlas.delete_eng_users_for_discord_id = AsyncMock(return_value=[10])
    interaction = interaction_factory()
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=atlas):
        await get_callback(cmd.eng_mongo_revoke)(cmd, interaction, "dev", member)
    assert "Revoked" in interaction.followup.send.await_args.kwargs["content"]
    assert "`dev`" in interaction.followup.send.await_args.kwargs["content"]


async def test_expire_eng_mongo_users_skips_unconfigured(mock_bot: MagicMock) -> None:
    cmd = _cmd(mock_bot)
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", return_value=None) as from_config:
        await cmd._expire_eng_mongo_users()
    assert from_config.call_count == 1


async def test_expire_eng_mongo_users_deletes_and_logs(mock_bot: MagicMock) -> None:
    cmd = _cmd(mock_bot)
    atlas = MagicMock()
    atlas.delete_expired_eng_users = AsyncMock(return_value=[10])

    def from_config(_config: object, project: str) -> MagicMock | None:
        return atlas if project == "dev" else None

    with patch("src.cogs.eng.mongo.AtlasClient.from_config", side_effect=from_config):
        await cmd._expire_eng_mongo_users()
    atlas.delete_expired_eng_users.assert_awaited_once()

    atlas.delete_expired_eng_users = AsyncMock(side_effect=AtlasAPIError(httpx.Response(500, json={"detail": "boom"})))
    with patch("src.cogs.eng.mongo.AtlasClient.from_config", side_effect=from_config):
        await cmd._expire_eng_mongo_users()
    mock_bot.logger.error.assert_called()


async def test_slash_eng_lifecycle(mock_bot: MagicMock) -> None:
    from src.cogs.eng import SlashEng

    mock_bot.wait_until_ready = AsyncMock()
    with (
        patch("discord.ext.tasks.Loop.start"),
        patch("discord.ext.tasks.Loop.is_running", return_value=False),
        patch("discord.ext.tasks.Loop.cancel"),
    ):
        cog = SlashEng(mock_bot)
        await cog.cog_unload()

    with patch.object(
        SlashEng,
        "__init__",
        lambda self, client: setattr(self, "client", client),
    ):
        cog = SlashEng(mock_bot)
    with patch.object(cog, "_expire_eng_mongo_users", new=AsyncMock()) as expire:
        await SlashEng.expire_eng_mongo_loop(cog)
        expire.assert_awaited_once()
    await SlashEng.before_expire_eng_mongo_loop(cog)
    mock_bot.wait_until_ready.assert_awaited()


async def test_slash_eng_skips_start_when_running(mock_bot: MagicMock) -> None:
    from discord.ext import tasks

    from src.cogs.eng import SlashEng

    def is_running_skip_start(self: object) -> bool:
        if not hasattr(self, "_last_iteration"):
            return False
        return True

    with (
        patch.object(tasks.Loop, "is_running", is_running_skip_start),
        patch.object(tasks.Loop, "start") as start,
        patch.object(tasks.Loop, "cancel"),
    ):
        SlashEng(mock_bot)
    start.assert_not_called()
