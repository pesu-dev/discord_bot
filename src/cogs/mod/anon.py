from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from src.cogs.mod.groups import ModGroups
from src.cogs.mod.helpers import ModHelpers
from src.utils import decorators as bot_decorators
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class AnonModCommands(ModHelpers):
    client: DiscordBot

    @ModGroups.mod_anon.command(name="ban", description="Ban a user from anon messaging using a message link or member")
    @app_commands.describe(
        member="The member to ban",
        link="The anon message link to ban from",
        time="Duration of the ban",
        reason="Reason for ban (optional)",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors()
    async def ban_anon(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        link: str | None = None,
        time: str | None = None,
        reason: str | None = "No reason provided",
    ) -> None:
        if (member is None) == (link is None):
            await interaction.followup.send(
                content="Specify exactly one of `member` or `link`",
                ephemeral=True,
            )
            return

        message_link: str | None = None
        if link is not None:
            user_to_ban = await self._handle_ban_message_link(interaction, link)
            if not user_to_ban:
                return
            message_link = link
        else:
            user_to_ban = member

        await self._apply_anon_ban(
            interaction,
            user_to_ban,
            time=time,
            reason=reason,
            message_link=message_link,
        )

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors()
    async def anon_ban_from_context_menu(self, interaction: discord.Interaction, message: discord.Message) -> None:
        ban_user = self._find_user_from_message(str(message.id), interaction.guild)
        if not ban_user:
            await interaction.followup.send(
                content="This wasn't an anon message only da what you doing?", ephemeral=True
            )
            return

        if await self._check_user_anon_ban(str(ban_user.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        reason = "No reason provided, executed via context menu"
        await self._create_and_store_ban(str(ban_user.id), reason, None)

        embed = ug.build_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": reason},
                {
                    "name": "Message Link",
                    "value": f"[Jump to message](https://discord.com/channels/{interaction.guild.id}/{interaction.channel.id}/{message.id})",
                },
                {"name": "Expires", "value": "Permanent"},
            ],
        )

        dm_sent = await ug.send_dm_safely(ban_user, embed)
        base_message = f"Member has been banned from anon messaging, their ban will never expire\nReason: {reason}"

        if dm_sent:
            await interaction.followup.send(content=base_message, ephemeral=True)
        else:
            await interaction.followup.send(
                content=f"{base_message} but I couldn't DM them",
                ephemeral=True,
            )

    @ModGroups.mod_anon.command(name="unban", description="Unban a user from anon messaging")
    @app_commands.describe(member="The member to unban")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors()
    async def user_unban_anon(self, interaction: discord.Interaction, member: discord.Member) -> None:
        result = await self.client.stores.anonbans.deactivate(str(member.id))

        if result is None:
            await interaction.followup.send(
                content="This fellow wasn't even anon-banned in the first place", ephemeral=True
            )
            return

        await interaction.followup.send(content="Member unbanned successfully")

        unban_embed = ug.build_embed(
            title="Notification",
            description="Your anon messaging ban has been revoked",
            color=discord.Color.green(),
        )

        if not await ug.send_dm_safely(member, unban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @ModGroups.mod_anon.command(name="info", description="Get info about a user's anon ban")
    @app_commands.describe(member="The member to get info about")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors()
    async def anon_ban_info(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ban = await self.client.stores.anonbans.find_one(user_id=str(member.id), active=True)
        if ban is None:
            await interaction.followup.send(content="This fellow is not banned from anon messaging", ephemeral=True)
            return

        expiry_display = discord.utils.format_dt(ban.expires_at, "R") if ban.expires_at else "Permanent"

        embed = ug.build_embed(
            title="Anon Ban Info",
            description="",
            color=discord.Color.red(),
            fields=[
                {"name": "User", "value": member.mention},
                {"name": "Reason", "value": ban.reason},
                {"name": "Banned", "value": discord.utils.format_dt(ban.banned_at, "R")},
                {"name": "Expires", "value": expiry_display},
            ],
        )

        await interaction.followup.send(embed=embed, ephemeral=True)
