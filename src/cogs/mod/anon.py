from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
            user_to_ban = await self._handle_anon_message_link(interaction, link)
            if not user_to_ban:
                return
            message_link = link
        else:
            user_to_ban = member

        await self._apply_anon_ban(
            interaction,
            user_to_ban,
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

        if await self.client.stores.anon_bans.has_active(str(ban_user.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        reason = "No reason provided, executed via context menu"
        await self._create_and_store_ban(str(ban_user.id), reason)

        embed = ug.build_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": reason},
                {
                    "name": "Message Link",
                    "value": (
                        f"[Jump to message](https://discord.com/channels/"
                        f"{interaction.guild.id}/{interaction.channel.id}/{message.id})"
                    ),
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
        result = await self.client.stores.anon_bans.unban(str(member.id), unbanned_at=datetime.now(UTC))

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

    @ModGroups.mod_anon.command(
        name="mute",
        description="Temporarily mute a user from anon messaging using a message link or member",
    )
    @app_commands.describe(
        member="The member to mute",
        link="The anon message link to mute from",
        time="Duration of the mute",
        reason="Reason for mute (optional)",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors()
    async def mute_anon(
        self,
        interaction: discord.Interaction,
        time: str,
        member: discord.Member | None = None,
        link: str | None = None,
        reason: str = "No reason provided",
    ) -> None:
        if (member is None) == (link is None):
            await interaction.followup.send(
                content="Specify exactly one of `member` or `link`",
                ephemeral=True,
            )
            return

        message_link: str | None = None
        if link is not None:
            user_to_mute = await self._handle_anon_message_link(interaction, link)
            if not user_to_mute:
                return
            message_link = link
        else:
            user_to_mute = member

        await self._apply_anon_mute(
            interaction,
            user_to_mute,
            time=time,
            reason=reason,
            message_link=message_link,
        )

    @ModGroups.mod_anon.command(name="unmute", description="Unmute a user from anon messaging")
    @app_commands.describe(member="The member to unmute")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors()
    async def unmute_anon(self, interaction: discord.Interaction, member: discord.Member) -> None:
        result = await self.client.stores.anon_mutes.unmute_user(str(member.id), unmuted_at=datetime.now(UTC))
        if result.modified_count == 0:
            await interaction.followup.send(
                content="This fellow wasn't even anon-muted in the first place",
                ephemeral=True,
            )
            return

        await interaction.followup.send(content="Member unmuted from anon messaging successfully")

        unmute_embed = ug.build_embed(
            title="Notification",
            description="Your anon messaging mute has been revoked",
            color=discord.Color.green(),
        )
        if not await ug.send_dm_safely(member, unmute_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @ModGroups.mod_anon.command(name="info", description="Get info about a user's anon ban and/or mute")
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
        user_id = str(member.id)
        ban, mute = await asyncio.gather(
            self.client.stores.anon_bans.find_active(user_id),
            self.client.stores.anon_mutes.find_active(user_id),
        )

        if ban is None and mute is None:
            await interaction.followup.send(
                content="This fellow has no active anon ban or mute",
                ephemeral=True,
            )
            return

        fields: list[dict] = [{"name": "User", "value": member.mention}]
        if ban is not None:
            fields.extend(
                [
                    {"name": "Ban Reason", "value": ban.reason},
                    {"name": "Banned", "value": discord.utils.format_dt(ban.banned_at, "R")},
                    {"name": "Ban Expires", "value": "Permanent"},
                ]
            )
        if mute is not None:
            fields.extend(
                [
                    {"name": "Mute Reason", "value": mute.reason},
                    {"name": "Muted", "value": discord.utils.format_dt(mute.muted_at, "R")},
                    {
                        "name": "Mute Expires",
                        "value": discord.utils.format_dt(mute.original_unmute_time, "R"),
                    },
                ]
            )

        embed = ug.build_embed(
            title="Anon Restriction Info",
            description="",
            color=discord.Color.red(),
            fields=fields,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
