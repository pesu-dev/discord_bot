from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.cogs.eng.commands import EngCommands
from src.cogs.eng.helpers import (
    DeviceCodeResponse,
    DeviceFlowAccessDeniedError,
    DeviceFlowError,
    DeviceFlowExpiredError,
    EngHelpers,
)
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory


@pytest.fixture(scope="module")
def sample_rsa_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("utf-8")


async def test_reload_single_invalid_cog(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    with patch("src.cogs.eng.helpers.resolve_cog_extension", side_effect=ValueError("unknown cog")):
        await helpers._reload_single_cog(interaction, "nope")
    assert "unknown cog" in interaction.followup.send.await_args.kwargs["content"]


async def test_reload_single_extension_failure(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    mock_bot.reload_extension = AsyncMock(side_effect=RuntimeError("boom" * 40))
    with patch("src.cogs.eng.helpers.resolve_cog_extension", return_value="src.cogs.eng"):
        await helpers._reload_single_cog(interaction, "eng")
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Failed to reload" in content
    assert "..." in content


async def test_reload_all_cogs_mixed(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    mock_bot.unload_extension = AsyncMock(side_effect=[None, RuntimeError("unload fail")])
    mock_bot.load_extension = AsyncMock(side_effect=[None, RuntimeError("load fail" * 20)])
    with patch("src.cogs.eng.helpers.discover_cog_extensions", return_value=["src.cogs.a", "src.cogs.b"]):
        with patch("src.cogs.eng.helpers.get_cogs_dir"):
            await helpers._reload_all_cogs(interaction)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Reloaded 1 cogs successfully" in content
    assert "Failed to unload" in content
    assert "Failed to load" in content


async def test_reload_all_cogs_success(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    mock_bot.unload_extension = AsyncMock()
    mock_bot.load_extension = AsyncMock()
    with patch("src.cogs.eng.helpers.discover_cog_extensions", return_value=["src.cogs.a", "src.cogs.b"]):
        with patch("src.cogs.eng.helpers.get_cogs_dir"):
            await helpers._reload_all_cogs(interaction)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Reloaded 2 cogs successfully" in content
    assert "Failed to unload" not in content
    assert "Failed to load" not in content


async def test_eng_reload_dispatches_single(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    with patch.object(cmd, "_reload_single_cog", new=AsyncMock()) as single:
        await get_callback(cmd.eng_reload)(cmd, interaction, cog="eng")
    single.assert_awaited_once()


async def test_eng_reload_dispatches_all(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    with patch.object(cmd, "_reload_all_cogs", new=AsyncMock()) as all_cogs:
        await get_callback(cmd.eng_reload)(cmd, interaction, cog=None)
    all_cogs.assert_awaited_once()


def test_mint_app_jwt(sample_rsa_key_pem: str) -> None:
    helpers = EngHelpers()
    token = helpers._mint_app_jwt(app_id="12345", private_key_pem=sample_rsa_key_pem)
    assert isinstance(token, str)
    assert len(token) > 0


def test_load_pem_key_success(tmp_path: pytest.TempPathFactory) -> None:
    helpers = EngHelpers()
    pem_file = tmp_path / "test.pem"  # type: ignore[operator]
    pem_file.write_text("dummy-pem-content", encoding="utf-8")
    assert helpers._load_pem_key(str(pem_file)) == "dummy-pem-content"


def test_load_pem_key_missing() -> None:
    helpers = EngHelpers()
    with pytest.raises(FileNotFoundError, match="GitHub App private key not found"):
        helpers._load_pem_key("nonexistent/path/to/key.pem")


@respx.mock
async def test_get_installation_token_success() -> None:
    helpers = EngHelpers()
    respx.post("https://api.github.com/app/installations/999/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "ghs_test_token"})
    )
    with (
        patch.object(helpers, "_load_pem_key", return_value="fake-pem"),
        patch.object(helpers, "_mint_app_jwt", return_value="fake-jwt"),
    ):
        token = await helpers._get_installation_token(app_id="123", installation_id="999", pem_key_path="dummy.pem")
    assert token == "ghs_test_token"


@respx.mock
async def test_get_installation_token_missing_token_in_json() -> None:
    helpers = EngHelpers()
    respx.post("https://api.github.com/app/installations/999/access_tokens").mock(
        return_value=httpx.Response(201, json={})
    )
    with (
        patch.object(helpers, "_load_pem_key", return_value="fake-pem"),
        patch.object(helpers, "_mint_app_jwt", return_value="fake-jwt"),
        pytest.raises(RuntimeError, match="missing 'token'"),
    ):
        await helpers._get_installation_token(app_id="123", installation_id="999", pem_key_path="dummy.pem")


@respx.mock
async def test_request_device_code_success() -> None:
    helpers = EngHelpers()
    respx.post("https://github.com/login/device/code").mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dev123",
                "user_code": "ABCD-1234",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
                "verification_uri_complete": "https://github.com/login/device?user_code=ABCD-1234",
            },
        )
    )
    resp = await helpers._request_device_code(client_id="client_test")
    assert isinstance(resp, DeviceCodeResponse)
    assert resp.device_code == "dev123"
    assert resp.user_code == "ABCD-1234"
    assert resp.verification_uri == "https://github.com/login/device"
    assert resp.expires_in == 900
    assert resp.interval == 5
    assert resp.verification_uri_complete == "https://github.com/login/device?user_code=ABCD-1234"


@respx.mock
async def test_request_device_code_failure() -> None:
    helpers = EngHelpers()
    respx.post("https://github.com/login/device/code").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await helpers._request_device_code(client_id="client_test")


@respx.mock
async def test_poll_device_token_immediate_success() -> None:
    helpers = EngHelpers()
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "ghu_valid_token"})
    )
    token = await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=1, timeout=10.0)
    assert token == "ghu_valid_token"


@respx.mock
async def test_poll_device_token_pending_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = EngHelpers()
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    route = respx.post("https://github.com/login/oauth/access_token")
    route.side_effect = [
        httpx.Response(200, json={"error": "authorization_pending"}),
        httpx.Response(200, json={"access_token": "ghu_success_after_pending"}),
    ]
    token = await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=1, timeout=10.0)
    assert token == "ghu_success_after_pending"
    assert route.call_count == 2


@respx.mock
async def test_poll_device_token_slow_down(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = EngHelpers()
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    route = respx.post("https://github.com/login/oauth/access_token")
    route.side_effect = [
        httpx.Response(200, json={"error": "slow_down"}),
        httpx.Response(200, json={"access_token": "ghu_after_slowdown"}),
    ]
    token = await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=2, timeout=10.0)
    assert token == "ghu_after_slowdown"
    assert route.call_count == 2


@respx.mock
async def test_poll_device_token_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = EngHelpers()
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"error": "expired_token"})
    )
    with pytest.raises(DeviceFlowExpiredError, match="has expired"):
        await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=1, timeout=10.0)


@respx.mock
async def test_poll_device_token_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = EngHelpers()
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"error": "access_denied"})
    )
    with pytest.raises(DeviceFlowAccessDeniedError, match="denied"):
        await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=1, timeout=10.0)


@respx.mock
async def test_poll_device_token_unknown_error(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = EngHelpers()
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"error": "bad_request", "error_description": "invalid client"})
    )
    with pytest.raises(DeviceFlowError, match="bad_request"):
        await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=1, timeout=10.0)


async def test_poll_device_token_timeout() -> None:
    helpers = EngHelpers()
    with pytest.raises(TimeoutError, match="timed out"):
        await helpers._poll_device_token(client_id="cid", device_code="dcode", interval=5, timeout=0.0)


@respx.mock
async def test_get_authenticated_user_success() -> None:
    helpers = EngHelpers()
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"id": 1234567, "login": "octocat"})
    )
    user_id, login = await helpers._get_authenticated_user("ghu_valid_token")
    assert user_id == 1234567
    assert login == "octocat"


@respx.mock
async def test_get_authenticated_user_failure() -> None:
    helpers = EngHelpers()
    respx.get("https://api.github.com/user").mock(return_value=httpx.Response(401))
    with pytest.raises(httpx.HTTPStatusError):
        await helpers._get_authenticated_user("ghu_bad_token")
