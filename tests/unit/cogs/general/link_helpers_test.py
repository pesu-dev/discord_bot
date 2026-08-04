"""Unit tests for `/link` orchestration in general helpers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx

from src.cogs.general.helpers import (
    ONBOARDING_CHECKLIST,
    GeneralHelpers,
    LinkMessage,
    PesuAuthProfile,
    PesuAuthResponse,
    _get_dm_message,
)
from src.data.mongo import Student
from src.utils import general as ug
from src.utils.config import Config

if TYPE_CHECKING:
    from tests.conftest import MemberFactory

AUTH_URL = Config.PESU_AUTH_URL
PROFILE = {
    "prn": "PES1202100001",
    "branch": "Computer Science and Engineering",
    "campus": "RR",
    "campusCode": 1,
}


def _helpers(mock_bot: MagicMock) -> GeneralHelpers:
    helpers = GeneralHelpers()
    helpers.client = mock_bot
    helpers.cached_data = None
    return helpers


def test_get_dm_message_includes_roles_and_channels() -> None:
    lobby = MagicMock()
    lobby.mention = "<#lobby>"
    text = _get_dm_message("CSE", "RR", "2021", lobby=lobby)
    assert "CSE" in text
    assert "RR" in text
    assert "2021" in text
    assert "<#lobby>" in text
    assert "`/togglerole`" in text


def test_pesu_auth_response_from_dict() -> None:
    response = PesuAuthResponse.from_dict(
        {
            "status": True,
            "message": "Login successful.",
            "timestamp": "2024-07-28 22:30:10.103368+05:30",
            "profile": {
                "name": "Johnny Blaze",
                "prn": "PES1201800001",
                "branch": "Computer Science and Engineering",
                "campus": "RR",
                "campusCode": 1,
            },
        }
    )
    assert response.status is True
    assert response.message == "Login successful."
    assert isinstance(response.profile, PesuAuthProfile)
    assert response.profile.prn == "PES1201800001"
    assert response.profile.campus_code == 1
    assert response.profile.missing_link_field() is None


def test_pesu_auth_profile_missing_link_field() -> None:
    profile = PesuAuthProfile(prn="PES1201800001", branch=None, campus="RR", campus_code=1)
    assert profile.missing_link_field() == "branch"


def test_pesu_auth_profile_has_na_link_field() -> None:
    profile = PesuAuthProfile(prn="PES1201800001", branch="NA", campus="RR", campus_code=1)
    assert profile.has_na_link_field() is True
    assert PesuAuthProfile(prn="PES1201800001", branch="CSE", campus="RR", campus_code=1).has_na_link_field() is False


def _auth_ok(profile: dict[str, object] | None = None) -> dict[str, object]:
    return {"status": True, "profile": profile or PROFILE}


@respx.mock
async def test_link_auth_failure(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": False, "message": "bad creds"}))
    member = member_factory()
    message, followup = await _helpers(mock_bot).link_account(member, "PES1UG21CS001", "wrong")
    assert message == LinkMessage.AUTH_FAILED
    assert followup is None
    await asyncio.sleep(0)
    mock_bot.config.error_logs_channel.send.assert_awaited()
    logged = mock_bot.config.error_logs_channel.send.await_args.kwargs["embed"].fields[0].value
    assert logged == "bad creds"


@respx.mock
async def test_link_missing_profile_field(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    bad = {**PROFILE, "branch": ""}
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok(bad)))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.MISSING_PROFILE_FIELDS
    assert followup is None


@respx.mock
async def test_link_onboarding_incomplete_na_field(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    bad = {**PROFILE, "branch": "NA"}
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok(bad)))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.ONBOARDING_INCOMPLETE
    assert followup == ONBOARDING_CHECKLIST


@respx.mock
async def test_link_unrecognized_branch(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    bad = {**PROFILE, "branch": "Unknown Branch"}
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok(bad)))
    mock_bot.config.resolve_academic_role = MagicMock(side_effect=ValueError("nope"))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.UNRECOGNIZED_BRANCH
    assert followup is None


@respx.mock
async def test_link_branch_short_code_fallback_uses_role_name(
    mock_bot: MagicMock, member_factory: MemberFactory
) -> None:
    """Auth returning a guild role name (not in BRANCH_SHORT_CODES) still links."""
    bad = {**PROFILE, "branch": "Psychology"}
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok(bad)))
    mock_bot.stores.links.exists = AsyncMock(return_value=False)
    mock_bot.stores.students.upsert_by_prn = AsyncMock()
    mock_bot.stores.links.insert_one = AsyncMock()
    member = member_factory(roles=[])
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    def resolve(name: str) -> MagicMock:
        if name in {"Psychology", "RR", "2021"}:
            return MagicMock(name=name)
        raise ValueError(name)

    mock_bot.config.resolve_academic_role = MagicMock(side_effect=resolve)

    with patch("src.cogs.general.helpers.ug.send_dm_safely", AsyncMock(return_value=True)):
        message, followup = await _helpers(mock_bot).link_account(member, "PES1UG21CS001", "x")

    assert message == LinkMessage.SUCCESS
    student_arg = mock_bot.stores.students.upsert_by_prn.await_args.args[0]
    assert student_arg.branch_long == "Psychology"
    assert student_arg.branch_short == "Psychology"
    assert followup is not None
    assert "Psychology" in followup


@respx.mock
async def test_link_missing_academic_role(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok()))
    mock_bot.config.resolve_academic_role = MagicMock(side_effect=ValueError("nope"))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.MISSING_ROLES
    assert followup is None


@respx.mock
async def test_link_prn_already_taken(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok()))
    mock_bot.stores.links.exists = AsyncMock(return_value=True)
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.PRN_TAKEN
    assert followup is None
    mock_bot.stores.students.upsert_by_prn.assert_not_called()


@respx.mock
async def test_link_success_runs_parallel_side_effects(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok()))
    mock_bot.stores.links.exists = AsyncMock(return_value=False)
    mock_bot.stores.students.upsert_by_prn = AsyncMock()
    mock_bot.stores.links.insert_one = AsyncMock()
    member = member_factory(roles=[mock_bot.config.just_joined_role])
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    with patch("src.cogs.general.helpers.ug.send_dm_safely", AsyncMock(return_value=True)) as send_dm:
        message, followup = await _helpers(mock_bot).link_account(member, "PES1UG21CS001", "secret")

    assert message == LinkMessage.SUCCESS
    assert followup is not None
    assert "Welcome to our humble little server" in followup
    assert "CSE" in followup
    assert ug.DM_AUTO_GENERATED_NOTICE not in followup
    mock_bot.stores.students.upsert_by_prn.assert_awaited()
    mock_bot.stores.links.insert_one.assert_awaited()
    member.add_roles.assert_awaited()
    member.remove_roles.assert_awaited_once_with(mock_bot.config.just_joined_role, reason="PESU account link")
    send_dm.assert_awaited()
    mock_bot.config.verification_logs_channel.send.assert_awaited()

    student_arg = mock_bot.stores.students.upsert_by_prn.await_args.args[0]
    assert isinstance(student_arg, Student)
    assert student_arg.prn == "PES1202100001"
    assert student_arg.branch_long == "Computer Science and Engineering"
    assert student_arg.branch_short == "CSE"
    assert student_arg.year == "2021"
    assert student_arg.campus == "RR"


@respx.mock
async def test_link_side_effect_failure_still_succeeds(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=_auth_ok()))
    mock_bot.stores.links.exists = AsyncMock(return_value=False)
    mock_bot.stores.students.upsert_by_prn = AsyncMock(side_effect=RuntimeError("mongo down"))
    mock_bot.stores.links.insert_one = AsyncMock()
    member = member_factory(roles=[])
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    with patch("src.cogs.general.helpers.ug.send_dm_safely", AsyncMock(return_value=True)):
        message, followup = await _helpers(mock_bot).link_account(member, "PES1UG21CS001", "secret")

    assert message == LinkMessage.SUCCESS
    assert followup is not None
    await asyncio.sleep(0)
    mock_bot.config.error_logs_channel.send.assert_awaited()


@respx.mock
async def test_link_non_prn_schedules_background_warning(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": False, "message": "fail"}))
    member = member_factory()

    with patch("src.cogs.general.helpers.asyncio.create_task") as create_task:

        def _capture(coro: object, **kwargs: object) -> MagicMock:
            if asyncio.iscoroutine(coro):
                coro.close()
            return MagicMock()

        create_task.side_effect = _capture
        message, followup = await _helpers(mock_bot).link_account(member, "teacher@pesu", "x")

    assert message == LinkMessage.AUTH_FAILED
    assert followup is None
    # Non-PRN warning + auth failure log
    assert create_task.call_count == 2
    assert all(call.kwargs.get("name") == "link-error-log" for call in create_task.call_args_list)


@respx.mock
async def test_link_http_error(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(side_effect=httpx.ConnectError("offline"))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.AUTH_FAILED
    assert followup is None
    await asyncio.sleep(0)
    mock_bot.config.error_logs_channel.send.assert_awaited()
    error_field = mock_bot.config.error_logs_channel.send.await_args.kwargs["embed"].fields[0]
    assert "offline" in error_field.value


@respx.mock
async def test_link_empty_http_body(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, content=b""))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.AUTH_FAILED
    assert followup is None


@respx.mock
async def test_link_non_json_body(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, content=b"not-json"))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.AUTH_FAILED
    assert followup is None


@respx.mock
async def test_link_json_non_dict(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json=[1, 2]))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.AUTH_FAILED
    assert followup is None


@respx.mock
async def test_link_profile_null(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": None}))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.MISSING_PROFILE_FIELDS
    assert followup is None
    await asyncio.sleep(0)
    mock_bot.config.error_logs_channel.send.assert_awaited()


async def test_link_defensive_missing_fields_after_fetch(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    helpers = _helpers(mock_bot)
    profile = MagicMock()
    profile.has_na_link_field.return_value = False
    profile.prn = None
    profile.branch = "CSE"
    profile.campus = "RR"
    profile.campus_code = 1
    with patch.object(helpers, "_fetch_link_profile", AsyncMock(return_value=profile)):
        message, followup = await helpers.link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.MISSING_PROFILE_FIELDS
    assert followup is None


@respx.mock
async def test_link_error_log_send_failure(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": False, "message": "bad"}))
    mock_bot.config.error_logs_channel.send = AsyncMock(side_effect=RuntimeError("channel gone"))
    message, followup = await _helpers(mock_bot).link_account(member_factory(), "PES1UG21CS001", "x")
    assert message == LinkMessage.AUTH_FAILED
    assert followup is None
    await asyncio.sleep(0)
    mock_bot.logger.exception.assert_called()
