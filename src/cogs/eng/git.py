from __future__ import annotations

from typing import TYPE_CHECKING

import discord
import httpx
from discord import app_commands

from src.cogs.eng.groups import EngGroups
from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EngGitCommands:
    client: DiscordBot

    @EngGroups.eng_git.command(name="join", description="Become part of the developer team")
    @app_commands.describe(
        user_id="Your GitHub user id",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.DEV_ENGINEER)
    @bot_decorators.handle_command_errors()
    async def join(self, interaction: discord.Interaction, user_id: int) -> None:
        url = "https://api.github.com/orgs/pesu-dev/invitations"
        token = self.client.config.github_org_token
        header = {
            "Authorization": f"Bearer {token}"  # use env variable for token
        }
        payload = {
            "invitee_id": user_id,  # put it as an integer
            "team_ids": [self.client.config.team_id],
        }
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, headers=header, json=payload, timeout=10.0)
                resp.raise_for_status()
                if resp.status_code == 201:
                    await interaction.followup.send(content="Sent invitation for organisation!")
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                self.client.logger.error(f"GitHub invite failed for '{user_id}': {status} - {exc.response.text}")

                if status == 404:
                    content = f"No GitHub user found for `{user_id}`."
                elif status == 422:
                    content = "This user may already be a member, or already has a pending invitation."
                elif status in (401, 403):
                    content = "The bot's GitHub credentials are misconfigured — please contact a maintainer."
                else:
                    content = "Something went wrong contacting GitHub. Please try again later."

                await interaction.followup.send(content=content)

            except httpx.RequestError as exc:
                self.client.logger.error(f"GitHub invite request failed for '{user_id}': {exc}")
                await interaction.followup.send(content="Couldn't reach GitHub right now. Please try again in a bit.")
