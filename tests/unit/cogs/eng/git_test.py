from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx

from src.cogs.eng.git import EngGitCommands
from src.cogs.eng.helpers import (
    DeviceCodeResponse,
    DeviceFlowAccessDeniedError,
    DeviceFlowExpiredError,
)
from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


def _setup_mock_bot(mock_bot: MagicMock) -> None:
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    mock_bot.config.github = MagicMock(
        client_id="test_client_id",
        app_id="123",
        installation_id="456",
        team_id="789",
    )
    mock_bot.config.github_app_private_key_path = "scratch/github-app.pem"


async def test_eng_git_join_requires_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.DEV
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)

    await cmd.join.callback(cmd, interaction)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.followup.send.assert_awaited_once()
    assert "not available in this environment" in interaction.followup.send.await_args.kwargs["content"]


def test_eng_git_join_is_ephemeral() -> None:
    cmd = EngGitCommands()
    assert getattr(cmd.join.callback, "_defer_ephemeral", None) is True


async def test_eng_git_join_existing_discord_user(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=MagicMock())

    await cmd.join.callback(cmd, interaction)
    interaction.followup.send.assert_awaited_once()
    assert "already exists" in interaction.followup.send.await_args.args[0]


async def test_eng_git_join_missing_credentials(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    mock_bot.config.github.client_id = None
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    await cmd.join.callback(cmd, interaction)
    interaction.followup.send.assert_awaited_once()
    assert "misconfigured" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_join_request_device_code_error(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    with patch.object(cmd, "_request_device_code", side_effect=RuntimeError("API error")):
        await cmd.join.callback(cmd, interaction)

    interaction.followup.send.assert_awaited_once()
    assert "Failed to initiate" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_join_timeout(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(side_effect=TimeoutError("Timed out"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.followup.send.assert_awaited_once()
    interaction.edit_original_response.assert_awaited_once()
    assert "timed out" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_access_denied(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(side_effect=DeviceFlowAccessDeniedError("denied"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "cancelled" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_expired(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(side_effect=DeviceFlowExpiredError("expired"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "expired" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_polling_unknown_error(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(side_effect=RuntimeError("unknown"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "Something went wrong" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_get_authenticated_user_fails(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(side_effect=RuntimeError("fetch user failed"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "Failed to retrieve" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_github_account_already_linked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)

    # find_one: first call checks discord_user_id (None), second checks github_user_id (found)
    mock_bot.stores.git_links.find_one = AsyncMock(side_effect=[None, MagicMock()])

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(return_value=(12345, "octocat"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "already linked" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_installation_token_error(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(return_value=(12345, "octocat"))),
        patch.object(cmd, "_get_installation_token", AsyncMock(side_effect=FileNotFoundError("missing pem"))),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "misconfigured" in interaction.edit_original_response.await_args.kwargs["content"]


@respx.mock
async def test_eng_git_join_success(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    respx.post("https://api.github.com/orgs/pesu-dev/invitations").mock(return_value=httpx.Response(201))

    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)
    mock_bot.stores.git_links.insert_one = AsyncMock()

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(return_value=(12345, "octocat"))),
        patch.object(cmd, "_get_installation_token", AsyncMock(return_value="inst_token")),
    ):
        await cmd.join.callback(cmd, interaction)

    mock_bot.stores.git_links.insert_one.assert_awaited_once()
    interaction.edit_original_response.assert_awaited_once()
    assert "Verified as **@octocat**" in interaction.edit_original_response.await_args.kwargs["content"]


@respx.mock
async def test_eng_git_join_invite_422(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    respx.post("https://api.github.com/orgs/pesu-dev/invitations").mock(
        return_value=httpx.Response(422, text="already member")
    )

    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(return_value=(12345, "octocat"))),
        patch.object(cmd, "_get_installation_token", AsyncMock(return_value="inst_token")),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "already be an organization member" in interaction.edit_original_response.await_args.kwargs["content"]


@respx.mock
async def test_eng_git_join_invite_401(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    respx.post("https://api.github.com/orgs/pesu-dev/invitations").mock(
        return_value=httpx.Response(401, text="unauthorized")
    )

    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(return_value=(12345, "octocat"))),
        patch.object(cmd, "_get_installation_token", AsyncMock(return_value="inst_token")),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "misconfigured" in interaction.edit_original_response.await_args.kwargs["content"]


@respx.mock
async def test_eng_git_join_invite_500(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    respx.post("https://api.github.com/orgs/pesu-dev/invitations").mock(
        return_value=httpx.Response(500, text="server error")
    )

    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    fake_device_code = DeviceCodeResponse(
        device_code="dcode",
        user_code="UCODE",
        verification_uri="https://github.com/login/device",
        expires_in=900,
        interval=5,
    )

    with (
        patch.object(cmd, "_request_device_code", AsyncMock(return_value=fake_device_code)),
        patch.object(cmd, "_poll_device_token", AsyncMock(return_value="valid_token")),
        patch.object(cmd, "_get_authenticated_user", AsyncMock(return_value=(12345, "octocat"))),
        patch.object(cmd, "_get_installation_token", AsyncMock(return_value="inst_token")),
    ):
        await cmd.join.callback(cmd, interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert "Something went wrong" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_join_missing_app_id_in_invite(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    _setup_mock_bot(mock_bot)
    mock_bot.config.github.app_id = None
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    await cmd._send_org_invitation(interaction, "1001", 12345, "octocat")
    interaction.edit_original_response.assert_awaited_once()
    assert "misconfigured" in interaction.edit_original_response.await_args.kwargs["content"]


async def test_eng_git_who_requires_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.LOCAL
    member = member_factory(roles=[mock_bot.config.bot_dev_role])
    interaction = interaction_factory(user=member)

    await cmd.who.callback(cmd, interaction, github_user="testuser")
    interaction.followup.send.assert_awaited_once()
    assert "not available in this environment" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_who_allows_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    member = member_factory(roles=[mock_bot.config.bot_dev_role])
    interaction = interaction_factory(user=member)

    await cmd.who.callback(cmd, interaction, member=None, github_user=None)
    interaction.followup.send.assert_awaited_once()
    assert "Please provide either" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_who_by_github_user_found(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    member = member_factory(roles=[mock_bot.config.bot_dev_role])
    interaction = interaction_factory(user=member)

    linked_mock = MagicMock(discord_user_id="1001", github_username="octocat")
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=linked_mock)

    await cmd.who.callback(cmd, interaction, github_user="octocat")
    interaction.followup.send.assert_awaited_once()
    assert "<@1001> (ID: 1001) is octocat" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_who_by_github_user_not_found(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    member = member_factory(roles=[mock_bot.config.bot_dev_role])
    interaction = interaction_factory(user=member)

    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    await cmd.who.callback(cmd, interaction, github_user="octocat")
    interaction.followup.send.assert_awaited_once()
    assert "No linked GitHub account found" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_who_by_member_found(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    caller = member_factory(roles=[mock_bot.config.bot_dev_role])
    target_member = member_factory(user_id=2002)
    interaction = interaction_factory(user=caller)

    linked_mock = MagicMock(discord_user_id="2002", github_username="octocat")
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=linked_mock)

    await cmd.who.callback(cmd, interaction, member=target_member)
    interaction.followup.send.assert_awaited_once()
    assert "<@2002> (ID: 2002) is octocat" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_who_by_member_not_found(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    caller = member_factory(roles=[mock_bot.config.bot_dev_role])
    target_member = member_factory(user_id=2002)
    interaction = interaction_factory(user=caller)

    mock_bot.stores.git_links.find_one = AsyncMock(return_value=None)

    await cmd.who.callback(cmd, interaction, member=target_member)
    interaction.followup.send.assert_awaited_once()
    assert "No linked GitHub account found" in interaction.followup.send.await_args.kwargs["content"]
