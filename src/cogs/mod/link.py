from __future__ import annotations

import discord
from discord import app_commands

from src.cogs.mod import ModGroups
from src.utils import general as ug


class LinkCommands:
    @ModGroups.mod_link.command(name="info", description="Get PESU account linking info about a user")
    @app_commands.describe(user="User to fetch PESU account linking info about")
    async def mod_link_info(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You are not authorised to run this command", ephemeral=True)
            return

        embed = discord.Embed(title="Link Info (Protected)", color=discord.Color.greyple())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="PESU Bot")

        link_record = await self.client.link_collection.find_one({"userId": str(user.id)})
        if not link_record:
            embed.add_field(name="Status", value="This user is not linked yet", inline=False)
            await interaction.followup.send(embed=embed)
            return

        if not link_record.get("prn"):
            embed.add_field(name="Error", value="Missing data!!!", inline=False)
            await interaction.followup.send(embed=embed)
            return

        embed.add_field(name="PRN", value=link_record["prn"], inline=False)
        await interaction.followup.send(embed=embed)

    @mod_link_info.error
    async def mod_link_info_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
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

    @ModGroups.mod_link.command(name="disconnect", description="Disconnect a user's PESU account from Discord")
    @app_commands.describe(user="User to disconnect")
    async def mod_link_disconnect(self, interaction: discord.Interaction, user: discord.Member) -> None:
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
            await user.remove_roles(*roles_to_remove, reason="Disconnecting")
            await user.add_roles(self.client.config.just_joined_role)
        except discord.Forbidden:
            await interaction.followup.send(
                content="I am unable to remove roles from this user although they were disconnected. Please check my permissions",  # noqa: E501
                ephemeral=True,
            )
            return

        await interaction.followup.send(content=f"Disconnected {user.mention}")

    @mod_link_disconnect.error
    async def mod_link_disconnect_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
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
