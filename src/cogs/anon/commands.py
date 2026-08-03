from __future__ import annotations

from datetime import UTC, datetime
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

    @AnonGroups.anon.command(
        name="send",
        description="Send messages anonymously to the general lobby channel",
    )
    @app_commands.describe(message="The message you want to send", link="Message link you want to reply to")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def anon_send(self, interaction: discord.Interaction, message: str, link: str | None = None) -> None:
        if not await self.client.stores.links.exists(user_id=str(interaction.user.id)):
            await interaction.followup.send(
                content="You're not linked, so you can't use anon messaging. If this is a mistake, please contact Han",
                ephemeral=True,
            )
            return
        if await self.client.stores.anonbans.exists(user_id=str(interaction.user.id), active=True):
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

        embed = ug.build_embed(
            title="Anon Message",
            color=discord.Color.random(),
            description=message,
        )

        if reply_msg:
            anon_message = await reply_msg.reply(embed=embed, mention_author=True)
        else:
            anon_message = await lobby_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(
            content=f":white_check_mark: Your anon message has been sent to {lobby_channel.mention}"
        )

        if str(interaction.user.id) not in self.client.anon_cache:
            self.client.anon_cache[str(interaction.user.id)] = []

        self.client.anon_cache[str(interaction.user.id)].append(
            {"message_id": str(anon_message.id), "timestamp": datetime.now(UTC)}
        )

    @AnonGroups.anon.command(
        name="vote",
        description="Vote for a poll",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def anon_vote(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send(
            content="Feature coming soon!",
            ephemeral=True,
        )
