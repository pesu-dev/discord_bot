from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.mod.groups import ModGroups
from src.cogs.mod.helpers import ModHelpers
from src.data.mongo import Mute
from src.utils import decorators as bot_decorators
from src.utils import general as ug
from src.utils.config import Config

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.bot import DiscordBot


class ModCommands(ModHelpers):
    client: DiscordBot

    @ModGroups.mod.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist here, who are you trying to kick?",
        forbidden="I am unable to kick this user at this time",
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if (target_error := ug.mod_target_error(member, self.client.config)) is not None:
            await interaction.followup.send(content=target_error, ephemeral=True)
            return

        await ug.send_dm_safely(
            member,
            content=f"You have been kicked from **{interaction.guild.name}**\nReason: {reason}",
        )

        await member.kick(reason=f"Kicked by {interaction.user} | {reason}")
        embed = ug.build_embed(
            title="Member Kicked",
            color=discord.Color.red(),
            description=f"{member.mention} was kicked by {interaction.user.mention}\n**Reason:** {reason}",
        )
        await interaction.followup.send(embed=embed)
        await self.client.config.mod_logs_channel.send(embed=embed)

    @ModGroups.mod.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(
        user="The user to ban (works even if they already left the server)",
        reason="Reason for the ban",
        delete_message_days="Days of the user's recent messages to delete (0-7)",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist, who are you trying to ban?",
        forbidden="I am unable to ban this user at this time",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str = "No reason provided",
        delete_message_days: int = 0,
    ) -> None:
        if not await self._validate_ban_args(interaction, reason, delete_message_days):
            return

        # Checks that apply whether or not the user is still in the server
        if user.id == interaction.user.id:
            await interaction.followup.send(content="You can't ban yourself", ephemeral=True)
            return
        if user.bot:
            await interaction.followup.send(content="Nope, not doing that again.", ephemeral=True)
            return

        # Read-only lookup before any mutation: a lookup failure aborts loudly, and a
        # malformed links record fails closed (no Discord ban without a recordable PRN).
        ban_prn, link_malformed = await self._lookup_server_ban_prn(user)
        if link_malformed:
            await interaction.followup.send(
                content=(
                    f"Ban NOT performed: {user.mention} has a malformed link record, so no PRN "
                    "identity ban could be established. Repair the `links` record before banning. "
                    "The member remains unbanned."
                ),
                ephemeral=True,
            )
            return

        # Role-hierarchy checks only make sense for current members
        member = interaction.guild.get_member(user.id)
        if member is not None:
            if (target_error := ug.mod_target_error(member, self.client.config)) is not None:
                await interaction.followup.send(content=target_error, ephemeral=True)
                return

            await ug.send_dm_safely(
                member,
                content=f"You have been banned from **{interaction.guild.name}**\nReason: {reason}",
            )

        # A reconciler cannot interleave this Discord + identity state transition.
        outcome, identity_prn = await self._ban_with_identity(interaction, user, ban_prn, reason, delete_message_days)

        embed = ug.build_embed(
            title="Member Banned",
            color=discord.Color.red(),
            description=self._ban_result_description(
                user_mention=user.mention,
                moderator_mention=interaction.user.mention,
                reason=reason,
                outcome=outcome,
                identity_prn=identity_prn,
            ),
        )
        await interaction.followup.send(embed=embed)

        # The ban already succeeded, so a log-channel failure must not look like a failed ban
        try:
            await self.client.config.mod_logs_channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to send ban log for user %s", user.id, exc_info=True)

    @ModGroups.mod.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(user="The user to unban", reason="Reason for the unban")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist, who are you trying to unban?",
        forbidden="I am unable to unban this user at this time",
    )
    async def unban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str = "No reason provided",
    ) -> None:
        if not 1 <= len(reason) <= 400:
            await interaction.followup.send(
                content="Reason must be between 1 and 400 characters",
                ephemeral=True,
            )
            return

        # Checks that apply whether or not the user is still in the server
        if user.id == interaction.user.id:
            await interaction.followup.send(content="You can't unban yourself", ephemeral=True)
            return
        if user.id == self.client.user.id:
            await interaction.followup.send(content="I'm not unbanning myself", ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.followup.send(content="You can't unban the server owner", ephemeral=True)
            return

        discord_banned, outcome, identity_prn, link_malformed = await self._unban_with_identity(
            interaction, user, reason
        )

        embed = ug.build_embed(
            title="Member Unbanned",
            color=discord.Color.green(),
            description=self._unban_result_description(
                user_mention=user.mention,
                moderator_mention=interaction.user.mention,
                reason=reason,
                discord_unbanned=discord_banned,
                outcome=outcome,
                identity_prn=identity_prn,
                link_malformed=link_malformed,
            ),
        )
        await interaction.followup.send(embed=embed)

        # The unban already succeeded, so a log-channel failure must not look like a failed unban
        try:
            await self.client.config.mod_logs_channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to send unban log for user %s", user.id, exc_info=True)

    @commands.hybrid_command(name="echo", aliases=["e"], description="Echoes a message to the target channel")
    @app_commands.guilds(discord.Object(id=Config.GUILD_ID))
    @app_commands.describe(
        channel="The channel to send the message to",
        message="The message to send",
        attachment="An optional attachment to send with the message",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="The specified channel does not exist",
        forbidden="I do not have permission to send messages in that channel",
    )
    async def echo(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | discord.Thread,
        attachment: discord.Attachment | None = None,
        *,
        message: str,
    ) -> None:
        file = await attachment.to_file() if attachment else None
        if file:
            await channel.send(content=message, file=file)
        else:
            await channel.send(content=message)
        await ctx.send(content=f"Message sent to {channel.mention}", ephemeral=True)

        echo_embed = ug.build_embed(
            title="Echo Sent",
            color=discord.Color.blue(),
            fields=[
                {"name": "Message", "value": message},
                {"name": "Channel", "value": channel.mention},
                {"name": "Attachment", "value": "Yes" if attachment else "No"},
                {"name": "Author", "value": ctx.author.mention},
            ],
        )
        await self.client.config.mod_logs_channel.send(embed=echo_embed)

    @ModGroups.mod.command(name="mute", description="Mute a member for a specified duration")
    @app_commands.describe(
        member="The member to mute",
        time="Duration for mute (e.g., 1h, 30m, 2d, and ofc y(💀))",
        reason="Reason for the mute (optional)",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist here, who are you trying to mute?",
        forbidden="I am unable to mute this user at this time",
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time: str,
        reason: str = "No reason provided",
    ) -> None:
        muted_role = self.client.config.muted_role

        try:
            seconds = ug.parse_time(time)
        except ValueError:
            await interaction.followup.send(
                content="Mention the proper amount of time\nAccepted Time Format: Should end with `d/h/m/s/y`",
                ephemeral=True,
            )
            return

        if muted_role in member.roles:
            await interaction.followup.send(
                content="Brother, leave the already muted poor soul alone",
                ephemeral=True,
            )
            return

        if (target_error := ug.mod_target_error(member, self.client.config)) is not None:
            await interaction.followup.send(content=target_error, ephemeral=True)
            return

        await member.add_roles(muted_role)
        mute_time = datetime.now(UTC)
        unmute_time = mute_time + timedelta(seconds=seconds)

        mute_record = Mute(
            discord_user_id=str(member.id),
            discord_channel_id=interaction.channel.id,
            moderator_discord_user_id=str(interaction.user.id),
            mute_time=mute_time,
            original_unmute_time=unmute_time,
            reason=reason,
        )
        await self.client.stores.mutes.insert_one(mute_record)

        unmute_relative = discord.utils.format_dt(unmute_time, "R")
        mute_embed = ug.build_embed(
            title="Mute",
            color=discord.Color.red(),
            fields=[
                {
                    "name": "Muted User",
                    "value": f"{member.mention} was muted\nUnmute: {unmute_relative}\nReason: {reason}",
                }
            ],
        )
        await interaction.followup.send(content=member.mention, embed=mute_embed)

        mute_logs_embed = ug.build_embed(
            title="Mute",
            color=discord.Color.red(),
            fields=[
                {
                    "name": "Muted User",
                    "value": (
                        f"{member.mention}\nTime: {time}\nReason: {reason}\nModerator: {interaction.user.mention}"
                    ),
                }
            ],
        )
        await self.client.config.mod_logs_channel.send(embed=mute_logs_embed)

    @ModGroups.mod.command(name="unmute", description="Unmute a member")
    @app_commands.describe(member="The member to unmute")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist here, who are you trying to unmute?",
        forbidden="I am unable to unmute this user at this time",
    )
    async def unmute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        muted_role = self.client.config.muted_role

        if muted_role not in member.roles:
            await interaction.followup.send(content="Why you trynna unmute someone who ain't muted?", ephemeral=True)
            return

        await member.remove_roles(muted_role)

        await self.client.stores.mutes.unmute_user(
            str(member.id),
            unmuted_at=datetime.now(UTC),
        )

        await interaction.followup.send(
            content=member.mention,
            embed=ug.build_embed(
                title="Unmute",
                color=discord.Color.green(),
                fields=[{"name": "Unmuted user", "value": f"{member.mention} welcome back"}],
            ),
        )
        await self.client.config.mod_logs_channel.send(
            embed=ug.build_embed(
                title="Unmute",
                color=discord.Color.green(),
                fields=[{"name": "Unmuted user", "value": f"{member.mention}\nModerator: {interaction.user.mention}"}],
            )
        )

    @ModGroups.mod.command(name="purge", description="Delete a number of recent messages")
    @app_commands.describe(amount="Number of messages to delete")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        forbidden="I am unable to delete messages in this channel at this time",
        not_found="This channel doesn't exist or has been deleted",
    )
    async def purge(self, interaction: discord.Interaction, amount: int) -> None:
        if amount < 1 or amount > 100:
            await interaction.followup.send(content="Please specify a number between 1 and 100", ephemeral=True)
            return

        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(content=f"Deleted last {len(deleted)} messages", ephemeral=True)
        embed = ug.build_embed(
            title="Messages Purged",
            color=discord.Color.green(),
            description=f"{interaction.user.mention} deleted {len(deleted)} messages in {interaction.channel.mention}",
        )
        await self.client.config.mod_logs_channel.send(embed=embed)

    @ModGroups.mod.command(name="lock", description="lock a channel")
    @app_commands.describe(
        channel="The channel to lock (defaults to current channel)",
        reason="Reason for locking the channel (optional)",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This channel doesn't exist or has been deleted",
        forbidden="I am unable to lock this channel at this time",
    )
    async def lock_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: str = "No reason provided",
    ) -> None:
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(
                    content="This command can only be used in a text channel",
                    ephemeral=True,
                )
                return
            channel = interaction.channel

        everyone_role = interaction.guild.default_role
        overwrites = channel.overwrites_for(everyone_role)
        overwrites.send_messages = False
        overwrites.send_messages_in_threads = False
        overwrites.create_public_threads = False
        overwrites.create_private_threads = False
        await channel.set_permissions(everyone_role, overwrite=overwrites)
        await interaction.followup.send(content=f"Locked {channel.mention}", ephemeral=False)

        lock_embed = ug.build_embed(
            title="Channel Locked :lock:",
            color=discord.Color.red(),
            description=reason,
        )
        await channel.send(embed=lock_embed)

        lock_logs_embed = ug.build_embed(
            title="Lock",
            color=discord.Color.red(),
            fields=[
                {"name": "Channel", "value": channel.mention, "inline": True},
                {"name": "Moderator", "value": interaction.user.mention, "inline": True},
                {"name": "Reason", "value": reason},
            ],
        )
        await self.client.config.mod_logs_channel.send(embed=lock_logs_embed)

    @ModGroups.mod.command(name="unlock", description="Unlock a channel")
    @app_commands.describe(channel="The channel to unlock (defaults to current channel)")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This channel doesn't exist or has been deleted",
        forbidden="I am unable to unlock this channel at this time",
    )
    async def unlock_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(
                    content="This command can only be used in a text channel",
                    ephemeral=True,
                )
                return
            channel = interaction.channel

        everyone_role = interaction.guild.default_role

        overwrites = channel.overwrites_for(everyone_role)
        overwrites.send_messages = None
        overwrites.send_messages_in_threads = None
        overwrites.create_public_threads = None
        overwrites.create_private_threads = None
        await channel.set_permissions(everyone_role, overwrite=overwrites)
        await interaction.followup.send(content=f"Unlocked {channel.mention}", ephemeral=False)

        unlock_embed = ug.build_embed(
            title="Channel Unlocked :unlock:",
            color=discord.Color.green(),
        )
        await channel.send(embed=unlock_embed)

        unlock_logs_embed = ug.build_embed(
            title="Unlock",
            color=discord.Color.green(),
            fields=[
                {"name": "Channel", "value": channel.mention, "inline": True},
                {"name": "Moderator", "value": interaction.user.mention, "inline": True},
            ],
        )
        await self.client.config.mod_logs_channel.send(embed=unlock_logs_embed)

    @ModGroups.mod.command(name="timeout", description="Timeout a member for a specified duration")
    @app_commands.describe(
        member="The member to timeout",
        time="Duration for timeout (e.g., 1h, 30m, 2d)",
        reason="Reason for the timeout (optional)",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist here, who are you trying to timeout?",
        forbidden="I am unable to timeout this user at this time",
    )
    async def timeout_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time: str,
        reason: str = "No reason provided",
    ) -> None:
        try:
            seconds = ug.parse_time(time)
        except ValueError:
            await interaction.followup.send(
                content=(
                    "Mention the proper amount of time to be timed-out\nAccepted Time Format: Should end with `d/h/m/s`"
                ),
                ephemeral=True,
            )
            return

        if seconds <= 0 or seconds > 2419200:
            await interaction.followup.send(content="Time-out limit is 28 days only", ephemeral=True)
            return

        if member.is_timed_out():
            await interaction.followup.send(
                content="Brother, leave the already timed-out poor soul alone", ephemeral=True
            )
            return

        if (target_error := ug.mod_target_error(member, self.client.config)) is not None:
            await interaction.followup.send(content=target_error, ephemeral=True)
            return

        timeout_until = datetime.now(UTC) + timedelta(seconds=seconds)
        await member.timeout(timeout_until, reason=reason)

        timeout_value = (
            f"{member.mention} was timed-out\n"
            f"De-time-out: {discord.utils.format_dt(timeout_until, 'R')}\n"
            f"Reason: {reason}"
        )
        timeout_embed = ug.build_embed(
            title="Time-out",
            color=discord.Color(0x8B0000),
            fields=[{"name": "Timed-out Member", "value": timeout_value}],
        )
        await interaction.followup.send(content=member.mention, embed=timeout_embed)

        timeout_logs_embed = ug.build_embed(
            title="Time-out",
            color=discord.Color(0x8B0000),
            fields=[
                {
                    "name": "Timed-out User",
                    "value": f"{member.mention}\nTime: {time}\nReason: {reason}\nModerator: {interaction.user.mention}",
                }
            ],
        )
        await self.client.config.mod_logs_channel.send(embed=timeout_logs_embed)

    @ModGroups.mod.command(name="detimeout", description="Remove timeout from a member")
    @app_commands.describe(member="The member to remove timeout from")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.ADMIN,
        bot_decorators.FunctionalRole.MOD,
        bot_decorators.FunctionalRole.JUNIOR_MOD,
    )
    @bot_decorators.handle_command_errors(
        not_found="This user doesn't even exist here, who are you trying to de-timeout?",
        forbidden="I am unable to de-timeout this user at this time",
    )
    async def detimeout_member(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not member.is_timed_out():
            await interaction.followup.send(content="This person ain't on time-out only", ephemeral=True)
            return

        await member.timeout(None, reason=f"Timeout removed by {interaction.user}")

        detimeout_embed = ug.build_embed(
            title="De-Time-out",
            color=discord.Color(0x00FF00),
            fields=[{"name": "De-timed-out Member", "value": f"{member.mention}, welcome back"}],
        )
        await interaction.followup.send(content=member.mention, embed=detimeout_embed)

        detimeout_logs_embed = ug.build_embed(
            title="De-time-out",
            color=discord.Color(0x00FF00),
            fields=[{"name": "De-timed-out User", "value": f"{member.mention}\nModerator: {interaction.user.mention}"}],
        )
        await self.client.config.mod_logs_channel.send(embed=detimeout_logs_embed)
