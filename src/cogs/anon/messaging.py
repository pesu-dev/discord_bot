from __future__ import annotations

import datetime

import discord
from discord import app_commands

from src.cogs.anon import AnonGroups
from src.utils import general as ug


class MessagingCommands:
    @AnonGroups.anon.command(
        name="send",
        description="Send messages anonymously to the general lobby channel",
    )
    @app_commands.describe(message="The message you want to send", link="Message link you want to reply to")
    async def anon_send(self, interaction: discord.Interaction, message: str, link: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(
                content="This command can only be used by members of the server", ephemeral=True
            )
            return

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

        # they passed the checks, so we can send the message

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

        # adds a list of dictionaries
        # each dict contains message id and timestamp
        self.anon_cache[str(interaction.user.id)].append(
            {"message_id": str(anon_message.id), "timestamp": datetime.datetime.now(datetime.UTC)}
        )

    @anon_send.error
    async def anon_send_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

