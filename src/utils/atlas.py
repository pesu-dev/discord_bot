"""Atlas Admin API client for temporary CUSTOMER X.509 database users."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

if TYPE_CHECKING:
    from src.utils.config import AtlasProject, Config

ATLAS_AUTH_DB = "$external"
SOURCE_LABEL_KEY = "source"
SOURCE_LABEL_VALUE = "bot-eng-mongo"
EXPIRES_LABEL_KEY = "expires"


class AtlasAPIError(Exception):
    """Raised when the Atlas Admin API returns an unexpected status."""

    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        try:
            self.detail = str(response.json()["detail"])[:300]
        except (ValueError, KeyError):
            self.detail = response.text[:300]
        super().__init__(f"Atlas API {self.status_code}: {self.detail}")


@dataclass(frozen=True, slots=True)
class AtlasDatabaseUser:
    """One Atlas database user, including our eng-mongo labels and description."""

    username: str
    discord_user_id: int
    description: str
    labels: dict[str, str]
    role: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> AtlasDatabaseUser | None:
        labels = {label["key"]: label["value"] for label in data["labels"]}
        if labels.get(SOURCE_LABEL_KEY) != SOURCE_LABEL_VALUE:
            return None
        username = data["username"]
        if not username.startswith("CN="):
            return None
        return cls(
            username=username,
            discord_user_id=int(username.removeprefix("CN=")),
            description=data["description"],
            labels=labels,
            role=data["roles"][0]["roleName"],
        )


class AtlasClient:
    """OAuth-authenticated Atlas Admin API client for one Atlas project."""

    def __init__(self, project: AtlasProject) -> None:
        self.project = project
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    @classmethod
    def from_config(cls, config: Config, project: str) -> AtlasClient | None:
        """Build a client for an Atlas project when service account credentials are present."""
        settings = config.atlas_projects.get(project)
        if settings is None or not all(
            (settings.client_id, settings.client_secret, settings.group_id, settings.cluster_name)
        ):
            return None
        return cls(settings)

    def _users_url(self, username: str | None = None) -> str:
        url = f"https://cloud.mongodb.com/api/atlas/v2/groups/{self.project.group_id}/databaseUsers"
        if username is None:
            return url
        db = quote(ATLAS_AUTH_DB, safe="")
        user = quote(username, safe="")
        return f"{url}/{db}/{user}"

    def _user_body(
        self,
        *,
        role_name: str,
        expires_at: int,
        description: str,
        username: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "databaseName": ATLAS_AUTH_DB,
            "x509Type": "CUSTOMER",
            "description": description,
            "labels": [
                {"key": SOURCE_LABEL_KEY, "value": SOURCE_LABEL_VALUE},
                {"key": EXPIRES_LABEL_KEY, "value": str(expires_at)},
            ],
            "roles": [{"databaseName": "admin", "roleName": role_name}],
            "scopes": [{"name": self.project.cluster_name, "type": "CLUSTER"}],
        }
        if username is not None:
            body["username"] = username
        return body

    async def _fetch_access_token(self) -> str:
        oauth_token_url = "https://cloud.mongodb.com/api/oauth/token"
        refresh_buffer_seconds = 60
        credentials = f"{self.project.client_id}:{self.project.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                oauth_token_url,
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
            )
        if response.status_code != 200:
            raise AtlasAPIError(response)
        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._token_expires_at = datetime.now(UTC).timestamp() + expires_in - refresh_buffer_seconds
        return self._access_token

    async def _get_access_token(self) -> str:
        if self._access_token and datetime.now(UTC).timestamp() < self._token_expires_at:
            return self._access_token
        return await self._fetch_access_token()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        expected: frozenset[int] = frozenset({200, 201}),
    ) -> httpx.Response:
        token = await self._get_access_token()
        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.atlas.2023-02-01+json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        ) as client:
            response = await client.request(method, url, json=json_body)
        if response.status_code not in expected:
            raise AtlasAPIError(response)
        return response

    async def _get_database_user(self, username: str) -> dict[str, Any] | None:
        response = await self._request(
            "GET",
            self._users_url(username),
            expected=frozenset({200, 404}),
        )
        if response.status_code == 404:
            return None
        return response.json()

    async def _delete_database_user(self, username: str) -> None:
        """Delete one database user by Atlas username (DN)."""
        await self._request(
            "DELETE",
            self._users_url(username),
            expected=frozenset({200, 202, 204}),
        )

    async def create_or_update_temp_user(
        self,
        *,
        discord_user_id: int,
        granted_by_id: int,
        role_name: str,
        hours: int,
    ) -> str:
        """Create a CUSTOMER user, or PATCH an existing grant. Returns ``Granted`` or ``Updated``."""
        if hours < 1 or hours > 8:
            raise ValueError("duration must be between 1 and 8 hours")
        username = f"CN={discord_user_id}"
        expires_at = int((datetime.now(UTC) + timedelta(hours=hours)).timestamp())
        description = json.dumps({"by": str(granted_by_id)}, separators=(",", ":"))
        create_body = self._user_body(
            role_name=role_name,
            expires_at=expires_at,
            description=description,
            username=username,
        )
        response = await self._request(
            "POST",
            self._users_url(),
            json_body=create_body,
            expected=frozenset({201, 409}),
        )
        if response.status_code == 409:
            existing = await self._get_database_user(username)
            if existing is None or AtlasDatabaseUser.from_api(existing) is None:
                raise ValueError(f"{username} already exists in Atlas and is not managed by /eng mongo")
            patch_body = self._user_body(
                role_name=role_name,
                expires_at=expires_at,
                description=description,
            )
            await self._request("PATCH", self._users_url(username), json_body=patch_body)
            return "Updated"
        return "Granted"

    async def list_eng_mongo_users(self) -> list[AtlasDatabaseUser]:
        """Database users created by /eng mongo."""
        response = await self._request("GET", f"{self._users_url()}?itemsPerPage=100")
        users: list[AtlasDatabaseUser] = []
        for row in response.json()["results"]:
            if user := AtlasDatabaseUser.from_api(row):
                users.append(user)
        return users

    async def delete_eng_users_for_discord_id(self, discord_user_id: int) -> list[int]:
        """Delete eng-mongo grants for a Discord user. Returns deleted Discord user ids."""
        deleted: list[int] = []
        for user in await self.list_eng_mongo_users():
            if user.discord_user_id != discord_user_id:
                continue
            await self._delete_database_user(user.username)
            deleted.append(user.discord_user_id)
        return deleted

    async def delete_expired_eng_users(self) -> list[int]:
        """Delete eng-mongo grants whose expires label is in the past."""
        deleted: list[int] = []
        now = int(datetime.now(UTC).timestamp())
        for user in await self.list_eng_mongo_users():
            if int(user.labels[EXPIRES_LABEL_KEY]) > now:
                continue
            await self._delete_database_user(user.username)
            deleted.append(user.discord_user_id)
        return deleted
