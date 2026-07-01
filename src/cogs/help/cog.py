from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.help.views import HelpEmbeds, HelpView, _has_linked_role
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashHelp(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

    @app_commands.command(name="help", description="Show the bot's help menu")
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        if not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        if not _has_linked_role(interaction.user, self.client):
            embed = HelpEmbeds(self.client).unlink[0]
            embed.set_footer(text="PESU Bot")
            await interaction.followup.send(embed=embed)
            return

        view = HelpView(interaction, self.client, category="anon", page=0)
        message = await interaction.followup.send(embed=view.get_embed(), view=view)
        view.message = message

    @help_command.error
    async def help_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
