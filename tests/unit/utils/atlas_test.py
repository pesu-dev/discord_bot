from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import quote

import httpx
import pytest
import respx

from src.utils.atlas import (
    ATLAS_AUTH_DB,
    SOURCE_LABEL_VALUE,
    AtlasAPIError,
    AtlasClient,
    AtlasDatabaseUser,
)
from src.utils.config import AtlasProject, Config

GROUP = "6a6bf379b0da6a50da88c661"
CLUSTER = "pesudev"
USERS_URL = f"https://cloud.mongodb.com/api/atlas/v2/groups/{GROUP}/databaseUsers"
OAUTH_TOKEN_URL = "https://cloud.mongodb.com/api/oauth/token"


def _client() -> AtlasClient:
    return AtlasClient(
        AtlasProject(client_id="client-id", client_secret="client-secret", group_id=GROUP, cluster_name=CLUSTER)
    )


def _mock_oauth(*, status_code: int = 200, access_token: str = "test-token") -> None:
    respx.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            status_code,
            json={"access_token": access_token, "expires_in": 3600, "token_type": "Bearer"},
        )
    )


def _user_url(username: str) -> str:
    return f"{USERS_URL}/{quote(ATLAS_AUTH_DB, safe='')}/{quote(username, safe='')}"


def _api_user(
    username: str,
    *,
    labels: list[dict[str, str]] | None = None,
    description: str = "",
    roles: list[str] | None = None,
) -> dict:
    return {
        "username": username,
        "description": description,
        "labels": labels or [],
        "roles": [{"roleName": name} for name in (roles or [])],
    }


async def test_create_rejects_bad_duration() -> None:
    client = _client()
    with pytest.raises(ValueError, match="duration"):
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_ro",
            hours=0,
        )
    with pytest.raises(ValueError, match="duration"):
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_ro",
            hours=9,
        )


def test_from_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_DEV_CLIENT_ID", raising=False)
    monkeypatch.delenv("ATLAS_DEV_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ATLAS_PROD_CLIENT_ID", raising=False)
    monkeypatch.delenv("ATLAS_PROD_CLIENT_SECRET", raising=False)
    config = Config(MagicMock(), env="local")
    assert AtlasClient.from_config(config, "dev") is None
    assert AtlasClient.from_config(config, "prod") is None
    assert AtlasClient.from_config(config, "staging") is None


def test_from_config_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("ATLAS_DEV_CLIENT_SECRET", "client-secret")
    config = Config(MagicMock(), env="prod")
    client = AtlasClient.from_config(config, "dev")
    assert client is not None
    assert client.project.group_id == GROUP
    assert client.project.cluster_name == CLUSTER
    assert AtlasClient.from_config(config, "prod") is None


@respx.mock
async def test_fetch_access_token() -> None:
    client = _client()
    _mock_oauth()
    token = await client._fetch_access_token()
    assert token == "test-token"
    oauth = respx.calls[0].request
    assert oauth.method == "POST"
    assert oauth.url == OAUTH_TOKEN_URL
    assert oauth.headers["authorization"].startswith("Basic ")
    assert oauth.content.decode() == "grant_type=client_credentials"


@respx.mock
async def test_fetch_access_token_error() -> None:
    client = _client()
    _mock_oauth(status_code=401)
    with pytest.raises(AtlasAPIError, match="401"):
        await client._fetch_access_token()


@respx.mock
async def test_create_temp_user() -> None:
    client = _client()
    _mock_oauth()
    username = "CN=10"
    respx.post(USERS_URL).mock(return_value=httpx.Response(201, json={"username": username}))
    assert (
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_ro",
            hours=8,
        )
        == "Granted"
    )
    posted = respx.calls[-1].request
    assert posted.method == "POST"
    assert posted.headers["authorization"] == "Bearer test-token"
    body = posted.content.decode()
    assert "CUSTOMER" in body
    assert "discord_ro" in body
    assert SOURCE_LABEL_VALUE in body
    assert "expires" in body
    assert "deleteAfterDate" not in body


@respx.mock
async def test_create_updates_on_conflict() -> None:
    client = _client()
    _mock_oauth()
    username = "CN=10"
    respx.post(USERS_URL).mock(return_value=httpx.Response(409, json={"detail": "exists"}))
    respx.get(_user_url(username)).mock(
        return_value=httpx.Response(
            200,
            json=_api_user(
                username,
                labels=[{"key": "source", "value": SOURCE_LABEL_VALUE}],
                description='{"by":"99"}',
                roles=["discord_ro"],
            ),
        )
    )
    respx.patch(_user_url(username)).mock(return_value=httpx.Response(200, json={"username": username}))
    assert (
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_rw",
            hours=2,
        )
        == "Updated"
    )


@respx.mock
async def test_create_conflict_with_unmanaged_user() -> None:
    client = _client()
    _mock_oauth()
    username = "CN=10"
    respx.post(USERS_URL).mock(return_value=httpx.Response(409, json={"detail": "exists"}))
    respx.get(_user_url(username)).mock(
        return_value=httpx.Response(200, json=_api_user(username, labels=[], roles=["discord_ro"]))
    )
    with pytest.raises(ValueError, match="not managed by /eng mongo"):
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_ro",
            hours=2,
        )


@respx.mock
async def test_create_http_error() -> None:
    client = _client()
    _mock_oauth()
    respx.post(USERS_URL).mock(return_value=httpx.Response(400, json={"detail": "bad role"}))
    with pytest.raises(AtlasAPIError, match="bad role") as exc:
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="nope",
            hours=1,
        )
    assert exc.value.status_code == 400


@respx.mock
async def test_create_error_non_json() -> None:
    client = _client()
    _mock_oauth()
    respx.post(USERS_URL).mock(return_value=httpx.Response(500, text="oops"))
    with pytest.raises(AtlasAPIError, match="oops"):
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_ro",
            hours=1,
        )


@respx.mock
async def test_list_eng_mongo_users() -> None:
    client = _client()
    _mock_oauth()
    respx.get(f"{USERS_URL}?itemsPerPage=100").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    _api_user("bot"),
                    _api_user("other", labels=[{"key": "source", "value": "other"}]),
                    _api_user(
                        "CN=10",
                        labels=[{"key": "source", "value": SOURCE_LABEL_VALUE}],
                        description='{"by":"99"}',
                        roles=["discord_ro"],
                    ),
                ]
            },
        )
    )
    users = await client.list_eng_mongo_users()
    assert len(users) == 1
    assert users[0].username == "CN=10"
    assert users[0].discord_user_id == 10


@respx.mock
async def test_delete_eng_users_for_discord_id() -> None:
    client = _client()
    _mock_oauth()
    username = "CN=10"
    respx.get(f"{USERS_URL}?itemsPerPage=100").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    _api_user(
                        username,
                        labels=[{"key": "source", "value": SOURCE_LABEL_VALUE}],
                        description='{"by":"99"}',
                        roles=["discord_ro"],
                    ),
                    _api_user(
                        "CN=11",
                        labels=[{"key": "source", "value": SOURCE_LABEL_VALUE}],
                        description='{"by":"99"}',
                        roles=["discord_ro"],
                    ),
                ]
            },
        )
    )
    respx.delete(_user_url(username)).mock(return_value=httpx.Response(204))
    deleted = await client.delete_eng_users_for_discord_id(10)
    assert deleted == [10]


@respx.mock
async def test_delete_none() -> None:
    client = _client()
    _mock_oauth()
    respx.get(f"{USERS_URL}?itemsPerPage=100").mock(return_value=httpx.Response(200, json={"results": []}))
    assert await client.delete_eng_users_for_discord_id(10) == []


@respx.mock
async def test_delete_expired_eng_users() -> None:
    client = _client()
    _mock_oauth()
    expired_name = "CN=10"
    live_name = "CN=11"
    now_ts = int(datetime.now(UTC).timestamp())
    respx.get(f"{USERS_URL}?itemsPerPage=100").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    _api_user(
                        expired_name,
                        labels=[
                            {"key": "source", "value": SOURCE_LABEL_VALUE},
                            {"key": "expires", "value": str(now_ts - 3600)},
                        ],
                        roles=["discord_ro"],
                    ),
                    _api_user(
                        live_name,
                        labels=[
                            {"key": "source", "value": SOURCE_LABEL_VALUE},
                            {"key": "expires", "value": str(now_ts + 8 * 3600)},
                        ],
                        roles=["discord_ro"],
                    ),
                ]
            },
        )
    )
    respx.delete(_user_url(expired_name)).mock(return_value=httpx.Response(204))
    deleted = await client.delete_expired_eng_users()
    assert deleted == [10]


def test_from_api_rejects_non_cn_username() -> None:
    data = _api_user(
        "bot",
        labels=[{"key": "source", "value": SOURCE_LABEL_VALUE}],
        roles=["discord_ro"],
    )
    assert AtlasDatabaseUser.from_api(data) is None


@respx.mock
async def test_create_conflict_user_not_found() -> None:
    client = _client()
    _mock_oauth()
    username = "CN=10"
    respx.post(USERS_URL).mock(return_value=httpx.Response(409, json={"detail": "exists"}))
    respx.get(_user_url(username)).mock(return_value=httpx.Response(404, json={"detail": "not found"}))
    with pytest.raises(ValueError, match="not managed by /eng mongo"):
        await client.create_or_update_temp_user(
            discord_user_id=10,
            granted_by_id=99,
            role_name="discord_ro",
            hours=2,
        )


def test_from_config_rejects_empty_strings() -> None:
    settings = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "group_id": "gid",
        "cluster_name": "cluster",
    }
    config = SimpleNamespace(atlas_projects={"dev": AtlasProject(**settings)})
    config.atlas_projects["dev"] = AtlasProject(**{**settings, "client_secret": ""})
    assert AtlasClient.from_config(config, "dev") is None
    config.atlas_projects["dev"] = AtlasProject(**{**settings, "group_id": ""})
    assert AtlasClient.from_config(config, "dev") is None
    config.atlas_projects["dev"] = AtlasProject(**{**settings, "cluster_name": ""})
    assert AtlasClient.from_config(config, "dev") is None
    assert AtlasClient.from_config(SimpleNamespace(atlas_projects={}), "dev") is None
