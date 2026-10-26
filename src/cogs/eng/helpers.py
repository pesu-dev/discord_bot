from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import discord
import httpx
import jwt

from src.data.mongo.collections.git_links import GitLink
from src.utils.general import COGS_PACKAGE, discover_cog_extensions, get_cogs_dir, resolve_cog_extension

if TYPE_CHECKING:
    from src.bot import DiscordBot


class DeviceFlowError(Exception):
    """Base exception for GitHub Device Flow errors."""


class DeviceFlowExpiredError(DeviceFlowError):
    """The device code has expired."""


class DeviceFlowAccessDeniedError(DeviceFlowError):
    """The user denied authorization."""


@dataclass(frozen=True, slots=True)
class DeviceCodeResponse:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    verification_uri_complete: str | None = None


class EngHelpers:
    client: DiscordBot

    async def _reload_single_cog(self, interaction: discord.Interaction, cog: str) -> None:
        try:
            extension = resolve_cog_extension(cog)
        except ValueError as e:
            await interaction.followup.send(content=str(e), ephemeral=True)
            return

        try:
            await self.client.reload_extension(extension)
            self.client.logger.info(f"Reloaded cog: {extension}")
            await interaction.followup.send(
                content=f"Reloaded 1 cog successfully.\n- `{extension}`",
                ephemeral=True,
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            self.client.logger.error(f"Failed to reload cog '{extension}': {error}")
            truncated = f"{error[:100]}{'...' if len(error) > 100 else ''}"
            await interaction.followup.send(
                content=f"Failed to reload 1 cog:\n- `{extension}`: {truncated}",
                ephemeral=True,
            )

    async def _reload_all_cogs(self, interaction: discord.Interaction) -> None:
        success: list[str] = []
        unload_failed: list[tuple[str, str]] = []
        load_failed: list[tuple[str, str]] = []

        extensions = discover_cog_extensions(get_cogs_dir(), COGS_PACKAGE)

        for cog_name in extensions:
            try:
                await self.client.unload_extension(cog_name)
                self.client.logger.info(f"Unloaded cog: {cog_name}")
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                unload_failed.append((cog_name, error))
                self.client.logger.warning(f"Failed to unload cog '{cog_name}' before reload: {error}")

        for cog_name in extensions:
            try:
                await self.client.load_extension(cog_name)
                self.client.logger.info(f"Reloaded cog: {cog_name}")
                success.append(cog_name)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                load_failed.append((cog_name, error))
                self.client.logger.error(f"Failed to load cog '{cog_name}' during reload: {error}")

        lines = [f"Reloaded {len(success)} cogs successfully."]
        if unload_failed:
            lines.append(f"Failed to unload {len(unload_failed)} cogs:")
            lines.extend(
                f"- `{cog_name}`: {error[:100]}{'...' if len(error) > 100 else ''}" for cog_name, error in unload_failed
            )
        if load_failed:
            lines.append(f"Failed to load {len(load_failed)} cogs:")
            lines.extend(
                f"- `{cog_name}`: {error[:100]}{'...' if len(error) > 100 else ''}" for cog_name, error in load_failed
            )

        await interaction.followup.send(content="\n".join(lines), ephemeral=True)

    def _mint_app_jwt(self, app_id: str, private_key_pem: str) -> str:
        now = int(time.time())
        payload = {
            "iat": now - 10,
            "exp": now + 60,
            "iss": app_id,
        }
        return jwt.encode(payload, private_key_pem, algorithm="RS256")

    def _load_pem_key(self, path: str) -> str:
        key_path = Path(path)
        if not key_path.is_file():
            msg = f"GitHub App private key not found at {path!r}"
            raise FileNotFoundError(msg)
        return key_path.read_text(encoding="utf-8")

    async def _get_installation_token(self, app_id: str, installation_id: str, pem_key_path: str) -> str:
        pem_key = self._load_pem_key(pem_key_path)
        jwt_token = self._mint_app_jwt(app_id=app_id, private_key_pem=pem_key)

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
            )
            res.raise_for_status()

            token = res.json().get("token")
            if not token:
                msg = "Github installation token response missing 'token'"
                raise RuntimeError(msg)
            return token

    async def _request_device_code(self, client_id: str, scope: str = "read:user") -> DeviceCodeResponse:
        """Request a device verification code from GitHub."""
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://github.com/login/device/code",
                headers={"Accept": "application/json"},
                data={"client_id": client_id, "scope": scope},
                timeout=10.0,
            )
            res.raise_for_status()
            data = res.json()
            return DeviceCodeResponse(
                device_code=data["device_code"],
                user_code=data["user_code"],
                verification_uri=data["verification_uri"],
                expires_in=int(data.get("expires_in", 900)),
                interval=int(data.get("interval", 5)),
                verification_uri_complete=data.get("verification_uri_complete"),
            )

    async def _poll_device_token(
        self,
        client_id: str,
        device_code: str,
        interval: int = 5,
        timeout: float = 300.0,
    ) -> str:
        """Poll GitHub for the user access token until granted, expired, denied, or timed out."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        poll_interval = max(interval, 1)

        async with httpx.AsyncClient() as client:
            while True:
                if loop.time() >= deadline:
                    msg = "Device flow authorization polling timed out"
                    raise TimeoutError(msg)

                res = await client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": client_id,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    timeout=10.0,
                )
                res.raise_for_status()
                data = res.json()

                if "access_token" in data:
                    return str(data["access_token"])

                error = data.get("error")
                if error == "authorization_pending":
                    pass
                elif error == "slow_down":
                    poll_interval += 5
                elif error == "expired_token":
                    msg = "The device verification code has expired"
                    raise DeviceFlowExpiredError(msg)
                elif error == "access_denied":
                    msg = "User denied authorization"
                    raise DeviceFlowAccessDeniedError(msg)
                else:
                    desc = data.get("error_description", "Unknown error")
                    msg = f"GitHub authorization failed ({error}): {desc}"
                    raise DeviceFlowError(msg)

                remaining = deadline - loop.time()
                if remaining <= 0:
                    msg = "Device flow authorization polling timed out"
                    raise TimeoutError(msg)
                await asyncio.sleep(min(poll_interval, remaining))

    async def _get_authenticated_user(self, access_token: str) -> tuple[int, str]:
        """Retrieve the authenticated GitHub user's numeric ID and login username."""
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
                timeout=10.0,
            )
            res.raise_for_status()
            data = res.json()
            return int(data["id"]), str(data["login"])

    async def _has_existing_discord_link(self, interaction: discord.Interaction, user_id: str) -> bool:
        link_record = await self.client.stores.git_links.find_one(discord_user_id=user_id)
        if link_record:
            await interaction.followup.send(
                "A GitHub account link already exists for this Discord user. "
                "Please contact Dev Staff if this is a mistake."
            )
            return True
        return False

    async def _start_device_flow(self, interaction: discord.Interaction) -> DeviceCodeResponse | None:
        client_id = self.client.config.github.client_id
        if not client_id or not self.client.config.github.app_id or not self.client.config.github.installation_id:
            await interaction.followup.send(
                content="The bot's GitHub credentials are misconfigured — please contact a maintainer."
            )
            return None

        try:
            device_code_data = await self._request_device_code(client_id=client_id)
        except Exception as exc:
            self.client.logger.error("Failed to request GitHub device code: %s", exc)
            await interaction.followup.send(content="Failed to initiate GitHub authorization. Please try again later.")
            return None

        auth_url = device_code_data.verification_uri_complete or device_code_data.verification_uri
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Authorize with GitHub", url=auth_url, style=discord.ButtonStyle.link))

        prompt_message = (
            "### 🐙 GitHub Account Verification\n\n"
            f"1. Open [GitHub Device Activation]({auth_url}) in your browser.\n"
            f"2. Confirm the code: **`{device_code_data.user_code}`**\n\n"
            "⏳ *Waiting for authorization (times out in 5 minutes)...*"
        )
        await interaction.followup.send(content=prompt_message, view=view)
        return device_code_data

    async def _await_authorization(
        self, interaction: discord.Interaction, device_code_data: DeviceCodeResponse
    ) -> str | None:
        client_id = self.client.config.github.client_id
        if not client_id:
            return None
        try:
            return await self._poll_device_token(
                client_id=client_id,
                device_code=device_code_data.device_code,
                interval=device_code_data.interval,
                timeout=300.0,
            )
        except TimeoutError:
            msg = "⏳ GitHub authorization timed out. Please run `/eng git join` again when you're ready."
        except DeviceFlowAccessDeniedError:
            msg = "❌ GitHub authorization was cancelled. Please run `/eng git join` again when you're ready."
        except DeviceFlowExpiredError:
            msg = "⏳ GitHub verification code expired. Please run `/eng git join` again."
        except Exception as exc:
            self.client.logger.error("Error during GitHub device flow polling: %s", exc)
            msg = "Something went wrong during GitHub authorization. Please try again later."

        await interaction.edit_original_response(content=msg, view=None)
        return None

    async def _fetch_and_validate_github_user(
        self, interaction: discord.Interaction, access_token: str
    ) -> tuple[int, str] | None:
        try:
            user_id, username = await self._get_authenticated_user(access_token)
        except Exception as exc:
            self.client.logger.error("Failed to retrieve GitHub user info: %s", exc)
            await interaction.edit_original_response(
                content="Failed to retrieve your GitHub account details. Please try again later.",
                view=None,
            )
            return None

        git_link = await self.client.stores.git_links.find_one(github_user_id=str(user_id))
        if not git_link:
            git_link = await self.client.stores.git_links.find_one(github_username=username.lower())
        if git_link:
            await interaction.edit_original_response(
                content=f"GitHub account **@{username}** is already linked to a Discord user. "
                "Please contact Dev Staff if this is a mistake.",
                view=None,
            )
            return None
        return user_id, username

    async def _send_org_invitation(
        self, interaction: discord.Interaction, discord_user_id: str, user_id: int, username: str
    ) -> None:
        app_id = self.client.config.github.app_id
        install_id = self.client.config.github.installation_id
        pem_key = self.client.config.github_app_private_key_path
        if not app_id or not install_id:
            await interaction.edit_original_response(
                content="The bot's GitHub credentials are misconfigured — please contact a maintainer.",
                view=None,
            )
            return

        try:
            token = await self._get_installation_token(app_id=app_id, installation_id=install_id, pem_key_path=pem_key)
        except (FileNotFoundError, httpx.HTTPStatusError, httpx.RequestError, RuntimeError) as exc:
            self.client.logger.error("Failed to get GitHub installation token: %s", exc)
            await interaction.edit_original_response(
                content="The bot's GitHub credentials are misconfigured — please contact a maintainer.",
                view=None,
            )
            return

        team_id = int(self.client.config.github.team_id) if self.client.config.github.team_id else None
        team_ids = [team_id] if team_id is not None else []
        url = "https://api.github.com/orgs/pesu-dev/invitations"
        header = {"Authorization": f"Bearer {token}"}
        payload = {
            "invitee_id": user_id,
            "team_ids": team_ids,
        }

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, headers=header, json=payload, timeout=10.0)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                self.client.logger.error("GitHub invite failed for '%s': %s - %s", username, status, exc.response.text)
                if status == 422:
                    content = (
                        f"You (**@{username}**) may already be an organization member, "
                        "or already have a pending invitation."
                    )
                elif status in (401, 403):
                    content = "The bot's GitHub credentials are misconfigured — please contact a maintainer."
                else:
                    content = "Something went wrong contacting GitHub to send your invitation. Please try again later."
                await interaction.edit_original_response(content=content, view=None)
                return

        git_record = GitLink(
            discord_user_id=discord_user_id,
            invited_at=datetime.now(UTC),
            github_username=username.lower(),
            github_user_id=str(user_id),
        )
        await self.client.stores.git_links.insert_one(git_record)
        await interaction.edit_original_response(
            content=f"✅ Verified as **@{username}**! Sent an invitation to the `pesu-dev` organization.",
            view=None,
        )
