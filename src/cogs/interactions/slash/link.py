import time

import discord
from discord import app_commands
from discord.ext import commands

import utils.general as ug
from bot import DiscordBot


class SlashLink(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

    @app_commands.command(name="info", description="Get linking info about a user")
    @app_commands.describe(user="User to fetch info about")
    async def info(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer()
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        created_at_timestamp = int(time.mktime(user.created_at.timetuple()))
        joined_at_timestamp = int(time.mktime(user.joined_at.timetuple())) if user.joined_at else None

        embed = discord.Embed(title="User Info", color=discord.Color.greyple())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Name", value=user.name, inline=True)
        embed.add_field(name="ID", value=str(user.id), inline=True)
        embed.add_field(name="Creation", value=f"<t:{created_at_timestamp}:R>", inline=True)
        if joined_at_timestamp:
            embed.add_field(name="Join", value=f"<t:{joined_at_timestamp}:R>", inline=True)
        embed.set_footer(text="PESU Bot")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

        if self.client.config.has_mod_permissions(interaction.user):
            mod_info_embed = discord.Embed(title="Priviliged Info", color=discord.Color.greyple())
            mod_info_embed.timestamp = discord.utils.utcnow()
            mod_info_embed.set_footer(text="PESU Bot")
            link_record = await self.client.link_collection.find_one({"userId": str(user.id)})

            if not link_record:
                mod_info_embed.add_field(name="Status", value="This user is not linked yet", inline=False)
                await interaction.followup.send(embed=mod_info_embed, ephemeral=True)
                return

            if not link_record.get("prn"):
                mod_info_embed.add_field(name="Error", value="Missing data!!!", inline=False)
                await interaction.followup.send(embed=mod_info_embed, ephemeral=True)
                return

            mod_info_embed.add_field(name="PRN", value=link_record["prn"], inline=False)

            await interaction.followup.send(embed=mod_info_embed, ephemeral=True)

    @info.error
    async def info_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            if isinstance(error.original, discord.NotFound):
                await interaction.followup.send(
                    content="The specified user does not exist or is not in the server",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="delink", description="Remove a user's linking")
    @app_commands.describe(user="User to delink")
    async def delink(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer()
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You are not authorised to run this command", ephemeral=True)
            return

        result = await self.client.link_collection.delete_one({"userId": str(user.id)})
        if result.deleted_count == 0:
            await interaction.followup.send(content="This user was not linked in the first place", ephemeral=True)
            return

        roles_to_remove = []
        for role in user.roles:
            if role.id != interaction.guild.id:
                roles_to_remove.append(role)

        try:
            await user.remove_roles(*roles_to_remove, reason="Delinking")
            await user.add_roles(self.client.config.just_joined_role)
        except discord.Forbidden:
            await interaction.followup.send(
                content="I am unable to remove roles from this user although they were delinked. Please check my permissions",  # noqa: E501
                ephemeral=True,
            )
            return

        await interaction.followup.send(content=f"De-linked {user.mention}")

    @delink.error
    async def delink_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            if isinstance(error.original, discord.NotFound):
                await interaction.followup.send(
                    content="The specified user does not exist or is not in the server",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashLink(client),
        guild=client.config.guild,
    )
