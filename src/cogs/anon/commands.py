from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from src.cogs.anon.groups import AnonGroups
from src.utils import decorators as bot_decorators
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class AnonCommands:
    client: DiscordBot
    anon_cache: dict

    @AnonGroups.anon.command(
        name="send",
        description="Send messages anonymously to the general lobby channel",
    )
    @app_commands.describe(message="The message you want to send", link="Message link you want to reply to")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def anon_send(self, interaction: discord.Interaction, message: str, link: str | None = None) -> None:
        member_link_check = await self.client.link_collection.find_one({"userId": str(interaction.user.id)})
        if not member_link_check:
            await interaction.followup.send(
                content="You're not linked, so you can't use anon messaging. If this is a mistake, please contact Han",
                ephemeral=True,
            )
            return
        member_anon_ban_check = await self.client.anonban_collection.find_one(
            {"userId": str(interaction.user.id), "active": True}
        )
        if member_anon_ban_check:
            await interaction.followup.send(
                content=":x: You have been banned from using anon messaging", ephemeral=True
            )
            return

        lobby_channel = self.client.config.lobby_channel
        perms = lobby_channel.permissions_for(interaction.user)
        if not perms.send_messages:
            await interaction.followup.send(
                content="Looks like the channel is locked or you're muted. I won't send",
                ephemeral=True,
            )
            return

        if link is not None:
            try:
                reply_msg = await lobby_channel.fetch_message(int(link.split("/")[-1]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                reply_msg = None
        else:
            reply_msg = None

        embed = discord.Embed(title="Anon Message", description=message, color=discord.Color.random())
        embed.timestamp = datetime.datetime.now(datetime.UTC)
        embed.set_footer(text="PESU Bot")

        if reply_msg:
            anon_message = await reply_msg.reply(embed=embed, mention_author=True)
        else:
            anon_message = await lobby_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(
            content=f":white_check_mark: Your anon message has been sent to {lobby_channel.mention}"
        )

        if str(interaction.user.id) not in self.anon_cache:
            self.anon_cache[str(interaction.user.id)] = []

        self.anon_cache[str(interaction.user.id)].append(
            {"message_id": str(anon_message.id), "timestamp": datetime.datetime.now(datetime.UTC)}
        )

    @AnonGroups.anon.command(name="ban", description="Ban a user from anon messaging using a message link or member")
    @app_commands.describe(
        member="The member to ban",
        link="The anon message link to ban from",
        time="Duration of the ban",
        reason="Reason for ban (optional)",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
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

        if user_to_ban is None:
            return

        await self._apply_anon_ban(
            interaction,
            user_to_ban,
            time=time,
            reason=reason,
            message_link=message_link,
        )

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
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

        embed = ug.build_notification_embed(
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

    @AnonGroups.anon.command(name="unban-user", description="Unban a user from anon messaging")
    @app_commands.describe(member="The member to unban")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
    @bot_decorators.handle_command_errors()
    async def user_unban_anon(self, interaction: discord.Interaction, member: discord.Member) -> None:
        result = await self.client.anonban_collection.find_one_and_update(
            {"userId": str(member.id), "active": True}, {"$set": {"active": False}}
        )

        if result is None:
            await interaction.followup.send(
                content="This fellow wasn't even anon-banned in the first place", ephemeral=True
            )
            return

        await interaction.followup.send(content="Member unbanned successfully")

        unban_embed = ug.build_notification_embed(
            title="Notification",
            description="Your anon messaging ban has been revoked",
            color=discord.Color.green(),
        )

        if not await ug.send_dm_safely(member, unban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @AnonGroups.anon.command(name="ban-info", description="Get info about a user's anon ban")
    @app_commands.describe(member="The member to get info about")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
    @bot_decorators.handle_command_errors()
    async def anon_ban_info(self, interaction: discord.Interaction, member: discord.Member) -> None:
        user_anon_ban_check = await self._check_user_anon_ban(str(member.id))
        if not user_anon_ban_check:
            await interaction.followup.send(content="This fellow is not banned from anon messaging", ephemeral=True)
            return

        banned_at = user_anon_ban_check["bannedAt"]
        expires_at = user_anon_ban_check["expiresAt"]
        expiry_timestamp = f"<t:{int(expires_at.timestamp())}:R>" if expires_at else "Permanent"

        embed = ug.build_notification_embed(
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
