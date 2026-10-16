from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
import httpx
from discord import app_commands

from src.cogs.eng.groups import EngGroups
from src.data.mongo.collections.git_links import GitLink
from src.utils import decorators as bot_decorators
from src.utils.git_helper import get_installation_token

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EngGitCommands:
    client: DiscordBot

    @EngGroups.eng_git.command(name="join", description="Become part of the developer team")
    @app_commands.describe(
        github_username="Your GitHub username",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.DEV_ENGINEER)
    @bot_decorators.handle_command_errors()
    async def join(self, interaction: discord.Interaction, github_username: str) -> None:
        user = interaction.user.id
        link_record = await self.client.stores.git_links.find_one(discord_user_id=str(user))
        username = str(github_username.strip().lower())
        git_link_record = await self.client.stores.git_links.find_one(github_username=username)
        if link_record or git_link_record:
            await interaction.followup.send(
                "A GitHub account link already exists for this Discord user or GitHub username. "
                "Please contact Dev Staff if this is a mistake"
            )
            return

        url_id = f"https://api.github.com/users/{username}"
        async with httpx.AsyncClient() as client:
            res = await client.get(url_id)
            if res.status_code == 404:
                await interaction.followup.send(
                    content=f"No GitHub user found with username `{github_username}`. "
                    "Please check the spelling and try again."
                )
                return
            content = res.json()
            user_id = content["id"]
            git_app_id = self.client.config.github.app_id
            git_app_install_id = self.client.config.github.installation_id
            git_private_key = self.client.config.github_app_private_key_path

            try:
                token = await get_installation_token(
                    app_id=git_app_id, installation_id=git_app_install_id, pem_key_path=git_private_key
                )
            except FileNotFoundError:
                await interaction.followup.send(
                    content="The bot's GitHub credentials are misconfigured — please contact a maintainer."
                )
                return
            except (httpx.HTTPStatusError, httpx.RequestError, RuntimeError) as exc:
                self.client.logger.error("Failed to get GitHub installation token: %s", exc)
                await interaction.followup.send(
                    content="The bot's GitHub credentials are misconfigured — please contact a maintainer."
                )
                return

            url = "https://api.github.com/orgs/pesu-dev/invitations"

            header = {
                "Authorization": f"Bearer {token}"  # use env variable for token
            }
            payload = {
                "invitee_id": user_id,  # put it as an integer
                "team_ids": [self.client.config.github.team_id],
            }

            try:
                resp = await client.post(url, headers=header, json=payload, timeout=10.0)
                resp.raise_for_status()
                if resp.status_code == 201:
                    git_record = GitLink(
                        discord_user_id=str(user),
                        invited_at=datetime.now(UTC),
                        github_username=username,
                        github_user_id=str(user_id),
                    )
                    await self.client.stores.git_links.insert_one(git_record)
                    await interaction.followup.send(content="Sent invitation for organisation!")

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                self.client.logger.error(
                    f"GitHub invite failed for '{github_username}': {status} - {exc.response.text}"
                )

                if status == 404:
                    content = f"No GitHub user found for `{github_username}`."
                elif status == 422:
                    content = "This user may already be a member, or already has a pending invitation."
                elif status in (401, 403):
                    content = "The bot's GitHub credentials are misconfigured — please contact a maintainer."
                else:
                    content = "Something went wrong contacting GitHub. Please try again later."

                await interaction.followup.send(content=content)

    @EngGroups.eng_git.command(name="who", description="Identify a given user")
    @app_commands.describe(
        member="Discord member to look up",
        github_user="GitHub username to look up",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.BOT_DEV)
    @bot_decorators.handle_command_errors()
    async def who(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        github_user: str | None = None,
    ) -> None:
        if github_user is not None:
            username = (github_user.strip()).lower()
            linked = await self.client.stores.git_links.find_one(github_username=username)
            target = github_user
        elif member is not None:
            disc_id = str(member.id)
            linked = await self.client.stores.git_links.find_one(discord_user_id=disc_id)
            target = member.mention
        elif github_user is None and member is None:
            await interaction.followup.send(
                content="Please provide either a member or a github_username, not both or neither."
            )
            return
        if linked is None:
            await interaction.followup.send(
                content=f"No linked GitHub account found for {target}.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        await interaction.followup.send(
            content=f"<@{linked.discord_user_id}> (ID: {linked.discord_user_id}) is {linked.github_username}"
        )
