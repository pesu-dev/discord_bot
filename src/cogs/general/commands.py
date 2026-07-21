from __future__ import annotations

import os
from typing import TYPE_CHECKING

import discord
import httpx
from discord import app_commands

from src.cogs.general.components import RoleSelectView
from src.utils import decorators as bot_decorators
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class GeneralCommands:
    client: DiscordBot
    cached_data: dict | None

    @app_commands.command(name="link", description="Link your PESU account to Discord")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    async def link(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send("Coming soon", ephemeral=True)

    @app_commands.command(name="info", description="Get info about a user")
    @app_commands.describe(user="User to fetch info about")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors(
        not_found="The specified user does not exist or is not in the server",
    )
    async def info(self, interaction: discord.Interaction, user: discord.Member) -> None:
        fields: list[dict] = [
            {"name": "Name", "value": user.name, "inline": True},
            {"name": "ID", "value": str(user.id), "inline": True},
            {"name": "Creation", "value": discord.utils.format_dt(user.created_at, "R"), "inline": True},
        ]
        if user.joined_at:
            fields.append({"name": "Join", "value": discord.utils.format_dt(user.joined_at, "R"), "inline": True})

        roles = [role.mention for role in user.roles if role != interaction.guild.default_role]
        roles_value = " ".join(roles) if roles else "None"
        if len(roles_value) > 1024:
            roles_value = f"{roles_value[:1021]}..."
        fields.append({"name": "Roles", "value": roles_value})

        embed = ug.build_embed(
            title="User Info",
            color=discord.Color.greyple(),
            fields=fields,
            thumbnail=user.display_avatar.url,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="count",
        description="Get the server stats or count members in specific roles",
    )
    @app_commands.describe(rolelist="List of roles to count members for, separated by &")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def count(self, interaction: discord.Interaction, rolelist: str | None = None) -> None:
        # Server stats
        total_count = interaction.guild.member_count
        linked_count = len(self.client.config.linked_role.members)
        channel_count = len(interaction.channel.members)
        bot_count = len([m for m in interaction.channel.members if m.bot])
        server_stats_content = "**Server Stats**"
        server_stats_content += f"\nTotal number of people on the server: `{total_count}`"
        server_stats_content += f"\nTotal number of linked people: `{linked_count}`"
        server_stats_content += f"\nNumber of people that can see this channel: `{channel_count}`"
        server_stats_content += f"\nNumber of bots that can see this channel: `{bot_count}`"

        if rolelist is None:
            await interaction.followup.send(content=server_stats_content)
        else:
            role_list = [role.strip() for role in rolelist.split("&") if role.strip()]
            role_objects = []
            for role_name in role_list:
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role is not None:
                    role_objects.append(role)

            if len(role_objects) == 0:
                await interaction.followup.send(content="No roles found. Processing request for server stats...")
                await interaction.followup.send(content=server_stats_content)

            else:
                common_members = set(role_objects[0].members)
                for role in role_objects[1:]:
                    common_members &= set(role.members)
                member_counts = len(common_members)

                role_names = [role.name for role in role_objects]
                role_names = ", ".join(role_names)
                wrd = "have" if member_counts > 1 or member_counts == 0 else "has"
                plural_or_single = "people" if member_counts > 1 or member_counts == 0 else "person"
                await interaction.followup.send(content=f"{member_counts} {plural_or_single} {wrd} [{role_names}]")

    @app_commands.command(name="spotify", description="Get your current Spotify details")
    @app_commands.describe(user="The user to get Spotify details for (default: you)")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def spotify(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        # discord.Interaction's user object doesn't receive presence data
        # we will have to fetch it from bot's cache instead
        member = interaction.guild.get_member(user.id if user else interaction.user.id)

        if member is None:
            await interaction.followup.send(content="User not found in this server.", ephemeral=True)
            return

        for activity in member.activities:
            if isinstance(activity, discord.Spotify):
                await interaction.followup.send(
                    content=f"Listening to `{activity.title}` by `{activity.artist}`\nSong link: {activity.track_url}",
                    ephemeral=False,
                )
                return
        await interaction.followup.send(content="No spotify activity detected", ephemeral=True)

    @app_commands.command(
        name="addroles",
        description="Pick up additional roles to get access to more channels",
    )
    @app_commands.describe(channel="The channel to send the role selection in (default: current channel)")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
    @bot_decorators.handle_command_errors()
    async def addroles_command(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        embed = ug.build_embed(
            title="Additional Roles",
            color=discord.Color.blurple(),
            description="Pick up additional roles for access to more channels",
        )

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(
                    content="This command can only be used in a text channel",
                    ephemeral=True,
                )
                return
            channel = interaction.channel
        view = RoleSelectView(self.client)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(content=f"Role selection sent in {channel.mention}", ephemeral=True)

    @app_commands.command(name="pride", description="Flourishes you with the pride of PESU")
    @app_commands.describe(link="The message link to reply with the pride to")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors(
        not_found="The specified message does not exist or is not in the channel",
        forbidden="I do not have permission to reply to that message",
    )
    async def pride(self, interaction: discord.Interaction, link: str | None = None) -> None:
        await interaction.followup.send(content="Pride of PESU coming your way...", ephemeral=False)
        if link is not None:
            try:
                message = await interaction.channel.fetch_message(int(link.split("/")[-1]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None
        else:
            message = None

        if message is not None:
            await message.reply(
                content="https://tenor.com/view/pes-pesuniversity-pesu-may-the-pride-of-pes-may-the-pride-of-pes-be-with-you-gif-21274060"
            )
        else:
            await interaction.followup.send(
                content="https://tenor.com/view/pes-pesuniversity-pesu-may-the-pride-of-pes-may-the-pride-of-pes-be-with-you-gif-21274060"
            )

    @app_commands.command(name="ask", description="Ask a question regarding PESU")
    @app_commands.describe(query="The question that needs to be answered")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def ask(self, interaction: discord.Interaction, query: str) -> None:
        url = os.getenv("ASKPESU_API")
        payload = {"query": query}
        try:
            async with httpx.AsyncClient(timeout=500) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data["answer"]
                    lines = answer.split("\n")
                    chunk = ""
                    chunks = []
                    for line in lines:
                        if len(chunk) + len(line) + 1 > 2000:
                            chunks.append(chunk)
                            chunk = ""

                        chunk += line + "\n"

                    if chunk.strip():
                        chunks.append(chunk)

                    ask_footer = "• Powered by AskPESU • I am an AI bot, and can make mistakes."
                    embeds_to_send = [
                        ug.build_embed(
                            title=f"{query}".capitalize() if i == 0 else "",
                            color=discord.Color.orange(),
                            description=c.strip(),
                            footer=f"{i + 1}/{len(chunks)} {ask_footer}",
                        )
                        for i, c in enumerate(chunks)
                    ]

                    await interaction.followup.send(embeds=embeds_to_send)

                else:
                    await interaction.followup.send(content=f"Request failed with status {resp.status_code}.")
        except Exception as e:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(e))

    @app_commands.command(name="faq", description="Read the FAQ for PESU")
    @app_commands.describe(
        category="Optional category of the FAQ",
        question="Optional specific question inside the category",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def faq(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        question: str | None = None,
    ) -> None:
        data = await self.get_data()

        if category and category not in data:
            await interaction.followup.send(content="Invalid category selected", ephemeral=True)
            return

        if question and not category:
            await interaction.followup.send(
                content="Please choose a category before selecting a question",
                ephemeral=True,
            )
            return

        if category and not question:
            await self._handle_category_only(interaction, data, category)
            return

        if question and category:
            await self._handle_specific_question(interaction, data, category, question)
            return

        await interaction.followup.send(
            content="[Read the full FAQ](https://www.reddit.com/r/PESU/comments/14c1iym/faqs/)",
            ephemeral=False,
        )

    @faq.autocomplete("category")
    async def category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        data = await self.get_data()
        return [app_commands.Choice(name=cat, value=cat) for cat in data.keys() if current.lower() in cat.lower()]

    @faq.autocomplete("question")
    async def question_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        data = await self.get_data()
        category = getattr(interaction.namespace, "category", None)

        if not category or category not in data:
            return [app_commands.Choice(name="⚠️ Select a category first", value="")]

        questions: list[str] = []
        for entry in data[category]:
            q = entry["question"]
            if current.lower() in q.lower():
                questions.append(q)

        return [app_commands.Choice(name=q[:100], value=q[:100]) for q in questions[:25]]
