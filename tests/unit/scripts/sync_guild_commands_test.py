from __future__ import annotations

from scripts.sync_guild_commands import extract_commands_from_source


def test_extract_slash_and_group_commands() -> None:
    source = """
import discord
from discord import app_commands
from discord.ext import commands

class ModGroups:
    mod = app_commands.Group(name="mod", description="mod")
    mod_link = app_commands.Group(name="link", description="link", parent=mod)

class ModCommands:
    @ModGroups.mod.command(name="kick", description="Kick")
    async def kick(self, interaction: discord.Interaction) -> None:
        pass

    @ModGroups.mod_link.command(name="info", description="Info")
    async def mod_link_info(self, interaction: discord.Interaction) -> None:
        pass

    @commands.hybrid_command(name="echo", description="Echo")
    async def echo(self, ctx: commands.Context) -> None:
        pass

    @app_commands.command(name="help", description="Help")
    async def help_command(self, interaction: discord.Interaction) -> None:
        pass

class SlashMod:
    def __init__(self) -> None:
        self.ctx_menu = app_commands.ContextMenu(name="Ban this anon", callback=self.cb)

    async def cb(self, interaction: discord.Interaction, message: discord.Message) -> None:
        pass
"""
    commands = extract_commands_from_source(source)
    assert "slash:mod kick" in commands
    assert "slash:mod link info" in commands
    assert "slash:echo" in commands
    assert "slash:help" in commands
    assert "context_menu:Ban this anon" in commands


def test_extract_commands_bad_syntax() -> None:
    assert extract_commands_from_source("def (") == set()
