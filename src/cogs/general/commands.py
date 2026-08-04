from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
import httpx
from discord import app_commands

from src.cogs.general.helpers import GeneralHelpers
from src.data.mongo import Mute
from src.utils import decorators as bot_decorators
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot

# Self-assignable optional roles
_TOGGLEABLE_ROLE_CHOICES = [
    app_commands.Choice(name="🎮 Gamer", value="778825985361051660"),
    app_commands.Choice(name="⌨️ Coder", value="778875127257104424"),
    app_commands.Choice(name="🎸 Musician", value="778875199701385216"),
    app_commands.Choice(name="🎥 Editor", value="782642024071168011"),
    app_commands.Choice(name="💡 Tech", value="790106229997174786"),
    app_commands.Choice(name="⚙️ Moto", value="836652197214421012"),
    app_commands.Choice(name="💸 Investors", value="936886064361144360"),
    app_commands.Choice(name="🤖 PESU Dev", value="810507351063920671"),
    app_commands.Choice(name="👀 NSFW", value="778820724424704011"),
]


class GeneralCommands(GeneralHelpers):
    client: DiscordBot
    cached_data: dict | None

    @app_commands.command(name="link", description="Link your PESU account to Discord")
    @app_commands.describe(
        username="PESU Academy username",
        password="PESU Academy password",
    )
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(
        bot_decorators.FunctionalRole.LINKED,
        forbid=True,
        message="This Discord user is already linked to a PESU Academy account",
    )
    @bot_decorators.handle_command_errors()
    async def link(self, interaction: discord.Interaction, username: str, password: str) -> None:
        message, followup = await self.link_account(interaction.user, username, password)
        await interaction.followup.send(content=message, ephemeral=True)
        if followup is not None:
            await interaction.followup.send(content=followup, ephemeral=True)

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
        name="togglerole",
        description="Toggle an optional role for yourself",
    )
    @app_commands.describe(role="The role to add or remove")
    @app_commands.choices(role=_TOGGLEABLE_ROLE_CHOICES)
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.LINKED)
    @bot_decorators.handle_command_errors()
    async def togglerole(self, interaction: discord.Interaction, role: str) -> None:
        assert isinstance(interaction.user, discord.Member)
        member = interaction.user
        discord_role = interaction.guild.get_role(int(role))
        if discord_role is None:
            await interaction.followup.send(content="Role not found", ephemeral=True)
            return

        if discord_role in member.roles:
            await member.remove_roles(discord_role)
            await interaction.followup.send(
                content=f"Removed the {discord_role.mention} role",
                ephemeral=True,
            )
        else:
            await member.add_roles(discord_role)
            await interaction.followup.send(
                content=f"You now have the {discord_role.mention} role",
                ephemeral=True,
            )

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

    @app_commands.command(name="selfmute", description="Mute yourself for a specified duration")
    @app_commands.describe(
        time="Duration for mute (e.g., 1h, 2h, 1d). Defaults to 1 hour. Minimum 1 hour.",
        reason="Reason for the mute (optional)",
    )
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors(
        forbidden="I am unable to mute you at this time",
    )
    async def selfmute(
        self,
        interaction: discord.Interaction,
        time: str | None = None,
        reason: str = "",
    ) -> None:
        assert isinstance(interaction.user, discord.Member)
        member = interaction.user
        muted_role = self.client.config.muted_role
        time_display = time if time is not None else "1h"

        if time is None:
            seconds = 3600
        else:
            try:
                seconds = ug.parse_time(time)
            except ValueError:
                await interaction.followup.send(
                    content="Mention the proper amount of time\nAccepted Time Format: Should end with `d/h/m/s/y`",
                    ephemeral=True,
                )
                return
            if seconds < 3600:
                await interaction.followup.send(content="Self-mute is only for 1 hour or more", ephemeral=True)
                return

        if muted_role in member.roles:
            await interaction.followup.send(
                content="Brother, how can you able to mute yourself when you are already muted?",
                ephemeral=True,
            )
            return

        await member.add_roles(muted_role, reason=reason)
        mute_time = datetime.now(UTC)
        unmute_time = mute_time + timedelta(seconds=seconds)

        mute_record = Mute(
            discord_user_id=str(member.id),
            discord_channel_id=interaction.channel.id,
            moderator_discord_user_id=str(member.id),
            mute_time=mute_time,
            original_unmute_time=unmute_time,
            reason=reason,
        )
        await self.client.stores.mutes.insert_one(mute_record)

        unmute_relative = discord.utils.format_dt(unmute_time, "R")
        mute_embed = ug.build_embed(
            title="Mute",
            color=discord.Color.red(),
            fields=[
                {
                    "name": "Muted User",
                    "value": f"{member.mention} was muted\nUnmute: {unmute_relative}\nReason: {reason}",
                }
            ],
        )
        await interaction.followup.send(content=member.mention, embed=mute_embed)

        mute_logs_embed = ug.build_embed(
            title="Mute",
            color=discord.Color.red(),
            fields=[
                {
                    "name": "Muted User",
                    "value": f"{member.mention}\nTime: {time_display}\nReason: {reason}\nModerator: Self",
                }
            ],
        )
        await self.client.config.mod_logs_channel.send(embed=mute_logs_embed)

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
