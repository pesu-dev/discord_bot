from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from src.cogs.eng.groups import EngGroups
from src.utils import decorators as bot_decorators
from src.utils.atlas import AtlasAPIError, AtlasClient

if TYPE_CHECKING:
    from src.bot import DiscordBot

_ENV_ROLES = {
    "dev": ("discord_ro", "discord_rw"),
    # "prod": ("default",), # This is not set up yet
}
_ENV_CHOICES = [app_commands.Choice(name=name, value=name) for name in _ENV_ROLES]


class EngMongoCommands:
    client: DiscordBot

    async def _expire_eng_mongo_users(self) -> None:
        for project in _ENV_ROLES:
            atlas = AtlasClient.from_config(self.client.config, project)
            if atlas is None:
                continue
            try:
                await atlas.delete_expired_eng_users()
            except AtlasAPIError as exc:
                self.client.logger.error("Failed to expire Atlas eng-mongo users (%s): %s", project, exc)

    @EngGroups.eng_mongo.command(name="access", description="Grant temporary MongoDB access to a member")
    @app_commands.describe(
        environment="Atlas project to grant access on",
        member="Member whose client cert CN is their Discord user id",
        role="Atlas custom role to assign",
        duration="Hours of access (1-8)",
    )
    @app_commands.choices(environment=_ENV_CHOICES)
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.BOT_DEV)
    @bot_decorators.handle_command_errors()
    async def eng_mongo_access(
        self,
        interaction: discord.Interaction,
        environment: str,
        member: discord.Member,
        role: str,
        duration: int,
    ) -> None:
        atlas = AtlasClient.from_config(self.client.config, environment)
        if atlas is None:
            await interaction.followup.send(content=f"Atlas admin is not configured for the `{environment}` project.")
            return

        allowed_roles = _ENV_ROLES.get(environment, ())
        if role not in allowed_roles:
            roles = ", ".join(f"`{name}`" for name in allowed_roles)
            await interaction.followup.send(content=f"Role must be one of: {roles}.")
            return

        try:
            action = await atlas.create_or_update_temp_user(
                discord_user_id=member.id,
                granted_by_id=interaction.user.id,
                role_name=role,
                hours=int(duration),
            )
        except AtlasAPIError as exc:
            await interaction.followup.send(content=f"Atlas rejected the request ({exc.status_code}): {exc.detail}")
            return
        except ValueError as exc:
            await interaction.followup.send(content=str(exc))
            return

        expires_at = int((datetime.now(UTC) + timedelta(hours=int(duration))).timestamp())
        expires = datetime.fromtimestamp(expires_at, UTC)
        await interaction.followup.send(
            content=(
                f"{action} `{role}` on `{environment}` to {member.mention} "
                f"until {discord.utils.format_dt(expires, 'f')} ({discord.utils.format_dt(expires, 'R')})."
            )
        )

    @eng_mongo_access.autocomplete("role")
    async def eng_mongo_access_role_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        environment = interaction.namespace.environment
        roles = _ENV_ROLES.get(environment, ()) if isinstance(environment, str) else ()
        if not roles:
            return [app_commands.Choice(name="Select an environment first", value="")]
        current_lower = current.lower()
        return [app_commands.Choice(name=role, value=role) for role in roles if current_lower in role.lower()]

    @EngGroups.eng_mongo.command(name="list", description="List temporary MongoDB access grants")
    @app_commands.describe(environment="Atlas project to list grants for")
    @app_commands.choices(environment=_ENV_CHOICES)
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.BOT_DEV)
    @bot_decorators.handle_command_errors()
    async def eng_mongo_list(self, interaction: discord.Interaction, environment: str) -> None:
        atlas = AtlasClient.from_config(self.client.config, environment)
        if atlas is None:
            await interaction.followup.send(content=f"Atlas admin is not configured for the `{environment}` project.")
            return

        try:
            users = await atlas.list_eng_mongo_users()
        except AtlasAPIError as exc:
            await interaction.followup.send(content=f"Atlas rejected the request ({exc.status_code}): {exc.detail}")
            return

        if not users:
            await interaction.followup.send(content=f"No temporary database users on `{environment}`.")
            return

        lines: list[str] = []
        for user in users:
            expires = datetime.fromtimestamp(int(user.labels["expires"]), UTC)
            granted_by = f" — granted by <@{json.loads(user.description)['by']}>"
            lines.append(
                f"- <@{user.discord_user_id}> — `{user.role}` — expires "
                f"{discord.utils.format_dt(expires, 'f')} ({discord.utils.format_dt(expires, 'R')}){granted_by}"
            )

        await interaction.followup.send(content=f"Temporary DB users (`{environment}`):\n" + "\n".join(lines))

    @EngGroups.eng_mongo.command(name="revoke", description="Revoke temporary MongoDB access for a member")
    @app_commands.describe(
        environment="Atlas project to revoke access on",
        member="Member whose temporary access should be removed",
    )
    @app_commands.choices(environment=_ENV_CHOICES)
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.BOT_DEV)
    @bot_decorators.handle_command_errors()
    async def eng_mongo_revoke(
        self, interaction: discord.Interaction, environment: str, member: discord.Member
    ) -> None:
        atlas = AtlasClient.from_config(self.client.config, environment)
        if atlas is None:
            await interaction.followup.send(content=f"Atlas admin is not configured for the `{environment}` project.")
            return

        try:
            deleted = await atlas.delete_eng_users_for_discord_id(member.id)
        except AtlasAPIError as exc:
            await interaction.followup.send(content=f"Atlas rejected the request ({exc.status_code}): {exc.detail}")
            return

        if not deleted:
            await interaction.followup.send(
                content=f"No temporary grant found for {member.mention} on `{environment}`."
            )
            return
        await interaction.followup.send(content=f"Revoked `{environment}` access for {member.mention}.")
