from __future__ import annotations

import discord
from discord import app_commands

from src.cogs.anon import AnonGroups
from src.utils import general as ug


class BanCommands:
    @AnonGroups.anon.command(name="ban", description="Ban a user from anon messaging using a message link or member")
    @app_commands.describe(
        member="The member to ban",
        link="The anon message link to ban from",
        time="Duration of the ban",
        reason="Reason for ban (optional)",
    )
    async def ban_anon(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        link: str | None = None,
        time: str | None = None,
        reason: str | None = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if (member is None) == (link is None):
            await interaction.followup.send(
                content="Specify exactly one of `member` or `link`",
                ephemeral=True,
            )
            return

        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        message_link: str | None = None
        if link is not None:
            if not await self._check_text_channel_permissions(interaction):
                return
            user_to_ban = await self._handle_ban_message_link(interaction, link)
            if not user_to_ban:
                return
            message_link = link
        else:
            user_to_ban = member

        if user_to_ban is None:
            return

        await self._apply_anon_ban(
            interaction,
            user_to_ban,
            time=time,
            reason=reason,
            message_link=message_link,
        )

    async def _apply_anon_ban(
        self,
        interaction: discord.Interaction,
        user_to_ban: discord.Member,
        *,
        time: str | None,
        reason: str | None,
        message_link: str | None = None,
    ) -> None:
        if await self._check_user_anon_ban(str(user_to_ban.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        if time is not None and await self._validate_and_parse_time(interaction, time) is None:
            return

        ban_reason = reason if reason is not None else "No reason provided"
        expiry_timestamp = await self._create_and_store_ban(str(user_to_ban.id), ban_reason, time)

        if expiry_timestamp == "Permanent":
            confirmation_msg = (
                f"Member has been banned from anon messaging, their ban will never expire\nReason: {ban_reason}"
            )
        else:
            confirmation_msg = (
                f"Member has been banned from anon messaging, their ban will expire {expiry_timestamp}\n"
                f"Reason: {ban_reason}"
            )

        await interaction.followup.send(content=confirmation_msg)

        ban_fields: list[dict] = [
            {"name": "Reason", "value": ban_reason},
            {"name": "Expires", "value": expiry_timestamp},
        ]
        if message_link is not None:
            ban_fields.insert(
                1,
                {"name": "Message Link", "value": f"[Click here to view the message]({message_link})"},
            )

        ban_embed = self._create_notification_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=ban_fields,
        )

        if not await self._send_dm_safely(user_to_ban, ban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @ban_anon.error
    async def ban_anon_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    async def anon_ban_from_context_menu(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return
        if not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
            return

        # Find user from message
        ban_user = self._find_user_from_message(str(message.id), interaction.guild)
        if not ban_user:
            await interaction.followup.send(
                content="This wasn't an anon message only da what you doing?", ephemeral=True
            )
            return

        # Check if user is already banned
        if await self._check_user_anon_ban(str(ban_user.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        # Create and store permanent ban
        reason = "No reason provided, executed via context menu"
        await self._create_and_store_ban(str(ban_user.id), reason, None)

        # Create notification embed
        embed = self._create_notification_embed(
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

        # Send DM and confirmation
        dm_sent = await self._send_dm_safely(ban_user, embed)
        base_message = f"Member has been banned from anon messaging, their ban will never expire\nReason: {reason}"

        if dm_sent:
            await interaction.followup.send(content=base_message, ephemeral=True)
        else:
            await interaction.followup.send(
                content=f"{base_message} but I couldn't DM them",
                ephemeral=True,
            )

    @AnonGroups.anon.command(name="unban-user", description="Unban a user from anon messaging")
    @app_commands.describe(member="The member to unban")
    async def user_unban_anon(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        # Attempt to unban user
        result = await self.client.anonban_collection.find_one_and_update(
            {"userId": str(member.id), "active": True}, {"$set": {"active": False}}
        )

        if result is None:
            await interaction.followup.send(
                content="This fellow wasn't even anon-banned in the first place", ephemeral=True
            )
            return

        await interaction.followup.send(content="Member unbanned successfully")

        # Send DM notification
        unban_embed = self._create_notification_embed(
            title="Notification",
            description="Your anon messaging ban has been revoked",
            color=discord.Color.green(),
        )

        if not await self._send_dm_safely(member, unban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @user_unban_anon.error
    async def user_unban_anon_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @AnonGroups.anon.command(name="ban-info", description="Get info about a user's anon ban")
    @app_commands.describe(member="The member to get info about")
    async def anon_ban_info(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        # Get ban info
        user_anon_ban_check = await self._check_user_anon_ban(str(member.id))
        if not user_anon_ban_check:
            await interaction.followup.send(content="This fellow is not banned from anon messaging", ephemeral=True)
            return

        banned_at = user_anon_ban_check["bannedAt"]
        expires_at = user_anon_ban_check["expiresAt"]
        expiry_timestamp = f"<t:{int(expires_at.timestamp())}:R>" if expires_at else "Permanent"

        # Create info embed
        embed = self._create_notification_embed(
            title="Anon Ban Info",
            description="",
            color=discord.Color.red(),
            fields=[
                {"name": "User", "value": member.mention},
                {"name": "Reason", "value": user_anon_ban_check.get("reason", "No reason provided")},
                {"name": "Banned", "value": f"<t:{int(banned_at.timestamp())}:R>"},
                {"name": "Expires", "value": expiry_timestamp},
            ],
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @anon_ban_info.error
    async def anon_ban_info_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
