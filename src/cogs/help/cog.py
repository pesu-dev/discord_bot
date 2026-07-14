from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.help.views import HelpEmbeds, HelpView
from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashHelp(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

    @app_commands.command(name="help", description="Show the bot's help menu")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def help_command(self, interaction: discord.Interaction) -> None:
        if self.client.config.linked_role not in interaction.user.roles:
            embed = HelpEmbeds(self.client).unlink[0]
            embed.set_footer(text="PESU Bot")
            await interaction.followup.send(embed=embed)
            return

        view = HelpView(interaction, self.client, category="anon", page=0)
        message = await interaction.followup.send(embed=view.get_embed(), view=view)
        view.message = message
