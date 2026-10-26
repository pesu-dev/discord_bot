from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from src.cogs.eng.groups import EngGroups
from src.cogs.eng.helpers import EngHelpers
from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EngGitCommands(EngHelpers):
    client: DiscordBot

    @EngGroups.eng_git.command(name="join", description="Become part of the developer team")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_env(bot_decorators.AppEnvironment.PROD)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.DEV_ENGINEER)
    @bot_decorators.handle_command_errors()
    async def join(self, interaction: discord.Interaction) -> None:
        user_id_str = str(interaction.user.id)
        if await self._has_existing_discord_link(interaction, user_id_str):
            return

        device_code_data = await self._start_device_flow(interaction)
        if not device_code_data:
            return

        access_token = await self._await_authorization(interaction, device_code_data)
        if not access_token:
            return

        user_info = await self._fetch_and_validate_github_user(interaction, access_token)
        if not user_info:
            return

        gh_id, gh_username = user_info
        await self._send_org_invitation(interaction, user_id_str, gh_id, gh_username)

    @EngGroups.eng_git.command(name="who", description="Identify a given user")
    @app_commands.describe(
        member="Discord member to look up",
        github_user="GitHub username to look up",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_env(bot_decorators.AppEnvironment.PROD)
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
