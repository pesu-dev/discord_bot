from __future__ import annotations

import json
import os
import time
from pathlib import Path

import discord
import httpx
from discord import app_commands

from src.cogs.utils.components import RoleSelectView
from src.utils import general as ug


class UtilsCommands:



    @app_commands.command(name="link", description="Link your PESU account to Discord")
    async def link(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Coming soon", ephemeral=True)

    @app_commands.command(name="info", description="Get info about a user")
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

        roles = [role.mention for role in user.roles if role != interaction.guild.default_role]
        roles_value = " ".join(roles) if roles else "None"
        if len(roles_value) > 1024:
            roles_value = f"{roles_value[:1021]}..."
        embed.add_field(name="Roles", value=roles_value, inline=False)

        embed.set_footer(text="PESU Bot")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

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

    @app_commands.command(
        name="count",
        description="Get the server stats or count members in specific roles",
    )
    @app_commands.describe(rolelist="List of roles to count members for, separated by &")
    async def count(self, interaction: discord.Interaction, rolelist: str | None = None) -> None:
        await interaction.response.defer()
        if not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send(
                content="This command can only be used in a text channel",
                ephemeral=True,
            )
            return

        # Server stats
        total_count = interaction.guild.member_count
        rolec = len(self.client.config.linked_role.members)
        channel_count = len(interaction.channel.members)
        bot_count = len([m for m in interaction.channel.members if m.bot])
        server_stats_content = "**Server Stats**"
        server_stats_content += f"\nTotal number of people on the server: `{total_count}`"
        server_stats_content += f"\nTotal number of linked people: `{rolec}`"
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

    @count.error
    async def count_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="spotify", description="Get your current Spotify details")
    @app_commands.describe(user="The user to get Spotify details for (default: you)")
    async def spotify(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        await interaction.response.defer()
        if not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        # discord.Interaction's user object doesn't receive presence data
        # we will have to fetch it from bot's cache instead
        realuser = interaction.guild.get_member(user.id if user else interaction.user.id)

        if realuser is None:
            await interaction.followup.send(content="User not found in this server.", ephemeral=True)
            return

        for activity in realuser.activities:
            if isinstance(activity, discord.Spotify):
                await interaction.followup.send(
                    content=f"Listening to `{activity.title}` by `{activity.artist}`\nSong link: {activity.track_url}",
                    ephemeral=False,
                )
                return
        await interaction.followup.send(content="No spotify activity detected", ephemeral=True)

    @spotify.error
    async def spotify_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(
        name="addroles",
        description="Pick up additional roles to get access to more channels",
    )
    @app_commands.describe(channel="The channel to send the role selection in (default: current channel)")
    async def addroles_command(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(
                content="This command can only be used in a server",
                ephemeral=True,
            )
            return
        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="Not to you lol", ephemeral=True)
            return
        embe = discord.Embed(
            title="Additional Roles",
            description="Pick up additional roles for access to more channels",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embe.set_footer(text="PESU Bot")

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(
                    content="This command can only be used in a text channel",
                    ephemeral=True,
                )
                return
            channel = interaction.channel
        view = RoleSelectView(self.client)
        await channel.send(embed=embe, view=view)
        await interaction.followup.send(content=f"Role selection sent in {channel.mention}", ephemeral=True)

    @addroles_command.error
    async def addroles_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="pride", description="Flourishes you with the pride of PESU")
    @app_commands.describe(link="The message link to reply with the pride to")
    async def pride(self, interaction: discord.Interaction, link: str | None = None) -> None:
        await interaction.response.defer()
        if not isinstance(interaction.channel, discord.TextChannel | discord.Thread):
            await interaction.followup.send(
                content="This command can only be used in a text channel",
                ephemeral=True,
            )
            return
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

    @pride.error
    async def pride_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            if isinstance(error.original, discord.NotFound):
                await interaction.followup.send(
                    content="The specified message does not exist or is not in the channel", ephemeral=True
                )
            elif isinstance(error.original, discord.Forbidden):
                await interaction.followup.send(
                    content="I do not have permission to reply to that message", ephemeral=True
                )
            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="ask", description="Ask a question regarding PESU")
    @app_commands.describe(query="The question that needs to be answered")
    async def ask(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
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

                    embeds_to_send = []
                    first_embed = discord.Embed(
                        title=f"{query}".capitalize(),
                        description=chunks[0].strip(),
                        color=discord.Color.orange(),
                        timestamp=discord.utils.utcnow(),
                    )
                    first_embed.set_footer(
                        text=f"1/{len(chunks)} • Powered by AskPESU • I am an AI bot, and can make mistakes."
                    )
                    embeds_to_send.append(first_embed)

                    for i, c in enumerate(chunks[1:]):
                        embed = discord.Embed(
                            description=c.strip(), color=discord.Color.orange(), timestamp=discord.utils.utcnow()
                        )
                        embed.set_footer(
                            text=f"{i + 2}/{len(chunks)} • Powered by AskPESU • I am an AI bot, and can make mistakes."
                        )
                        embeds_to_send.append(embed)

                    await interaction.followup.send(embeds=embeds_to_send)

                else:
                    await interaction.followup.send(content=f"Request failed with status {resp.status_code}.")
        except Exception as e:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(e))

    @ask.error
    async def ask_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    async def fetch_data(self) -> dict:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",  # noqa: E501
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        url = "https://reddit.com/r/PESU/comments/14c1iym/.json"

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return self._parse_reddit_data(data)

            resp = response.text
            self.client.logger.warning(
                f"Failed to fetch data: {response.status_code}, falling back to local data. {resp}"
            )
            return self._load_local_faq()

    @staticmethod
    def _load_local_faq() -> dict:
        faq_path = Path(__file__).resolve().parent.parent / "data" / "faq.json"
        with open(faq_path) as file:
            raw = json.load(file)

        data: dict = {}
        for category in raw.get("categories", []):
            name = category["category"]
            entries = data.setdefault(name, [])
            for item in category.get("questions", []):
                entries.append({"question": item["question"], "answer": item["answer"]})
        return data

    def _parse_reddit_data(self, data: dict) -> dict:
        x = data[0]["data"]["children"][0]["data"]["selftext"]
        finedata = {}
        y = x.split("# ")

        for i in y:
            j = i.split("\n\n")
            if "This post will be" in j[0]:
                continue

            s = j[1].split("* ")
            news = list(filter(None, s))

            for item in news:
                self._process_news_item(item, j[0], finedata)

        return finedata

    def _process_news_item(self, item: str, category: str, finedata: dict) -> None:
        if ") or [" in item:
            self._process_multiple_links(item, category, finedata)
        else:
            self._process_single_link(item, category, finedata)

    def _process_multiple_links(self, item: str, category: str, finedata: dict) -> None:
        chakdeh = item.split(") or [")
        for link_part in chakdeh:
            link_parts = link_part.split("](")
            title, url = self._clean_link_parts(link_parts)
            finedata.setdefault(category, []).append({"question": title, "answer": url})

    def _process_single_link(self, item: str, category: str, finedata: dict) -> None:
        chakdeh = item.split("](")
        title, url = self._clean_link_parts(chakdeh)
        if url.endswith("\n"):
            url = url[:-1]
        finedata.setdefault(category, []).append({"question": title, "answer": url})

    @staticmethod
    def _clean_link_parts(parts: list) -> tuple[str, str]:
        title, url = parts[0], parts[1]
        if title.startswith("["):
            title = title[1:]
        if url.endswith(")"):
            url = url[:-1]
        return title, url

    async def get_data(self) -> dict:
        if not self.cached_data:
            self.cached_data = await self.fetch_data()
        return self.cached_data

    @app_commands.command(name="faq", description="Read the FAQ for PESU")
    @app_commands.describe(
        category="Optional category of the FAQ",
        question="Optional specific question inside the category",
    )
    async def faq(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        question: str | None = None,
    ) -> None:
        await interaction.response.defer()
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

    async def _handle_category_only(self, interaction: discord.Interaction, data: dict, category: str) -> None:
        questions = []
        for entry in data[category]:
            question = entry["question"]
            answer = entry["answer"]
            if answer.endswith(")") or question.endswith("\n"):
                answer = answer[:-1]
            questions.append(f"[{question}]({answer})")

        if questions:
            embed = discord.Embed(
                title=f"FAQ - {category}",
                description="\n\n".join(questions),
                color=discord.Color.blurple(),
            )
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="FAQ",
                description="No questions found in this category",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def _handle_specific_question(
        self,
        interaction: discord.Interaction,
        data: dict,
        category: str,
        question: str,
    ) -> None:
        for entry in data[category]:
            if entry["question"] == question:
                url = entry["answer"]
                if url.endswith(")") or url.endswith("\n"):
                    url = url[:-1]
                await interaction.followup.send(content=f"[{question}]({url})", ephemeral=False)
                return

        await interaction.followup.send(content="Question not found in the selected category", ephemeral=True)

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

    @faq.error
    async def faq_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
