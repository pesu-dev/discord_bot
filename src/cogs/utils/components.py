from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import Interaction, SelectOption

if TYPE_CHECKING:
    from src.bot import DiscordBot


class RoleSelect(discord.ui.Select):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        options = [
            SelectOption(
                label="None",
                value="0",
                description="Use this to de-select your choice in this menu",
            ),
            SelectOption(
                label="Gamer",
                value="778825985361051660",
                description="Don't ever question Minecraft logic",
                emoji="🎮",
            ),
            SelectOption(
                label="Coder",
                value="778875127257104424",
                description="sudo apt install system32",
                emoji="⌨️",
            ),
            SelectOption(
                label="Musician",
                value="778875199701385216",
                description="From Pink Floyd to Prateek Kuhad",
                emoji="🎸",
            ),
            SelectOption(
                label="Editor",
                value="782642024071168011",
                description="A peek behind-the-scenes",
                emoji="🎥",
            ),
            SelectOption(
                label="Tech",
                value="790106229997174786",
                description="Pure Linus Sex Tips",
                emoji="💡",
            ),
            SelectOption(
                label="Moto",
                value="836652197214421012",
                description="Stutututu",
                emoji="⚙️",
            ),
            SelectOption(
                label="Investors",
                value="936886064361144360",
                description="Stocks and Crypto are your friends",
                emoji="💸",
            ),
            SelectOption(
                label="PESU Dev",
                value="810507351063920671",
                description="Join the PESU Dev team",
                emoji="🤖",
            ),
            SelectOption(
                label="NSFW",
                value="778820724424704011",
                description="Definitely not safe for anything",
                emoji="👀",
            ),
        ]
        super().__init__(
            placeholder="Additional Roles",
            custom_id="add_roles_select",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        role_id = self.values[0]

        if not isinstance(member, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        if self.client.config.linked_role not in member.roles:
            await interaction.followup.send(content="You need to link your account first.", ephemeral=True)
            return

        if role_id == "0":
            await interaction.followup.send(content="OK", ephemeral=True)
            return

        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.followup.send(content="Role not found", ephemeral=True)
            return

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.followup.send(
                content=f"Role {role.mention} was already present. Removing now...",
                ephemeral=True,
            )
        else:
            await member.add_roles(role)
            await interaction.followup.send(content=f"You now have the {role.mention} role", ephemeral=True)
        return


class RoleSelectView(discord.ui.View):
    def __init__(self, client: DiscordBot) -> None:
        super().__init__(timeout=None)
        self.add_item(RoleSelect(client))
