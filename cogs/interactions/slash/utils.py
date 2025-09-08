import discord
import utils.general as ug
from discord import app_commands, Interaction, SelectOption
from discord.ext import commands
import json
from pathlib import Path
from bot import DiscordBot
import httpx


class RoleSelect(discord.ui.Select):
    def __init__(self):
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

    async def callback(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        role_id = self.values[0]

        if not isinstance(member, discord.Member):
            return await interaction.followup.send(
                "This command can only be used in a server", ephemeral=True
            )
        if not interaction.guild:
            return await interaction.followup.send(
                "This command can only be used in a server", ephemeral=True
            )
        if any(role.id == ug.load_role_id("JUST_JOINED") for role in member.roles):
            await interaction.followup.send(
                "You need to link your account first.", ephemeral=True
            )
            return

        if role_id == "0":
            await interaction.followup.send("OK", ephemeral=True)
            return

        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.followup.send("Role not found", ephemeral=True)
            return

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.followup.send(
                f"Role {role.mention} was already present. Removing now...",
                ephemeral=True,
            )
        else:
            await member.add_roles(role)
            await interaction.followup.send(
                f"You now have the {role.mention} role", ephemeral=True
            )


class RoleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleSelect())


class SlashUtils(commands.Cog):
    def __init__(self, client: DiscordBot):
        self.client = client
        self.cached_data = None
        self.client.add_view(RoleSelectView())

    @app_commands.command(name="ping", description="Get the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(
            content=f"Pong!!!\nPing = `{round(self.client.latency * 1000)}ms`"
        )

    @ping.error
    async def ping_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="uptime", description="Get the bot's uptime")
    async def uptime(self, interaction: discord.Interaction):
        await interaction.response.defer()
        start = getattr(self.client, "startTime", None)
        if start is None:
            await interaction.followup.send(
                content="Uptime not available. Please restart the bot."
            )
        else:
            unixtmstmp = int(start)
            relative = f"<t:{unixtmstmp}:R>"
            longdatewithshorttime = f"<t:{unixtmstmp}:f>"

            await interaction.followup.send(
                content=f"Bot was started {relative}\ni.e., on {longdatewithshorttime}"
            )

    @uptime.error
    async def uptime_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="support", description="Contribute to bot development")
    async def support(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(
            content="You can contribute to the bot here\nhttps://github.com/pesu-dev/discord-bot"
        )

    @support.error
    async def support_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @staticmethod
    def get_linked_count(guild: discord.Guild) -> int:
        role = discord.utils.get(guild.roles, id=ug.load_role_id("LINKED"))
        if role is None:
            return 0
        return len(role.members)

    @app_commands.command(
        name="count",
        description="Get the server stats or count members in specific roles",
    )
    @app_commands.describe(
        rolelist="List of roles to count members for, separated by &"
    )
    async def count(
        self, interaction: discord.Interaction, rolelist: str | None = None
    ):
        await interaction.response.defer()
        if not interaction.guild:
            return await interaction.followup.send(
                "This command can only be used in a server", ephemeral=True
            )
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.followup.send(
                "This command can only be used in a text channel", ephemeral=True
            )
        if rolelist is None:
            rolec = type(self).get_linked_count(interaction.guild)
            await interaction.followup.send(
                content=f"**Server Stats**\n"
                f"Total number of people on the server: `{interaction.guild.member_count}`\n"
                f"Total number of linked people: `{rolec}`\n"
                f"Number of people that can see this channel: `{len(interaction.channel.members)}`\n"
                f"Number of bots that can see this channel: `{len([m for m in interaction.channel.members if m.bot])}`\n"
            )
        else:
            roleList = [role.strip() for role in rolelist.split("&") if role.strip()]
            roleObjects = []
            for roleName in roleList:
                role = discord.utils.get(interaction.guild.roles, name=roleName)
                if role is not None:
                    roleObjects.append(role)

            if len(roleObjects) == 0:
                await interaction.followup.send(
                    content="No roles found. Processing request for server stats..."
                )
                rolec = type(self).get_linked_count(interaction.guild)
                await interaction.followup.send(
                    content=f"**Server Stats**\n"
                    f"Total number of people on the server: `{interaction.guild.member_count}`\n"
                    f"Total number of linked people: `{rolec}`\n"
                    f"Number of people that can see this channel: `{len(interaction.channel.members)}`\n"
                    f"Number of bots that can see this channel: `{len([m for m in interaction.channel.members if m.bot])}`\n"
                )

            else:
                common_members = set(roleObjects[0].members)
                for role in roleObjects[1:]:
                    common_members &= set(role.members)
                memberCounts = len(common_members)

                roleNames = [role.name for role in roleObjects]
                wrd = "have" if memberCounts > 1 or memberCounts == 0 else "has"
                pluralorsingle = (
                    "people" if memberCounts > 1 or memberCounts == 0 else "person"
                )
                await interaction.followup.send(
                    content=f"{memberCounts} {pluralorsingle} {wrd} [{', '.join(roleNames)}]"
                )

    @count.error
    async def count_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(
        name="spotify", description="Get your current Spotify details"
    )
    @app_commands.describe(user="The user to get Spotify details for (default: you)")
    async def spotify(
        self, interaction: discord.Interaction, user: discord.User | None = None
    ):
        await interaction.response.defer()
        if not interaction.guild:
            return await interaction.followup.send(
                "This command can only be used in a server", ephemeral=True
            )
        realuser = interaction.guild.get_member(
            user.id if user else interaction.user.id
        )  # discord.Interaction's user object doesn't receive presence data, we will have to fetch it from bot's cache instead

        if realuser is None:
            await interaction.followup.send(
                content="User not found in this server.", ephemeral=True
            )
            return

        for activity in realuser.activities:
            if isinstance(activity, discord.Spotify):
                await interaction.followup.send(
                    content=f"Listening to `{activity.title}` by `{activity.artist}`\nSong link: {activity.track_url}",
                    ephemeral=False,
                )
                return
        await interaction.followup.send(
            content="No spotify activity detected", ephemeral=True
        )

    @spotify.error
    async def spotify_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(
        name="addroles",
        description="Pick up additional roles to get access to more channels",
    )
    @app_commands.describe(
        channel="The channel to send the role selection in (default: current channel)"
    )
    async def addroles_command(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not ug.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="Not to you lol", ephemeral=True)
            return
        embe = discord.Embed(
            title="Additional Roles",
            description="Pick up additional roles to get access to more channels",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embe.set_footer(text="PESU Bot")

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.followup.send(
                    "This command can only be used in a text channel", ephemeral=True
                )
            channel = interaction.channel
        view = RoleSelectView()
        await channel.send(embed=embe, view=view)
        await interaction.followup.send(
            content=f"Role selection sent in {channel.mention}", ephemeral=True
        )

    @addroles_command.error
    async def addroles_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(
        name="pride", description="Flourishes you with the pride of PESU"
    )
    @app_commands.describe(link="The message link to reply with the pride to")
    async def pride(self, interaction: discord.Interaction, link: str | None = None):
        await interaction.response.send_message(
            "Pride of PESU coming your way...", ephemeral=False
        )
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.followup.send(
                "This command can only be used in a text channel", ephemeral=True
            )
        if link is not None:
            try:
                message = await interaction.channel.fetch_message(
                    int(link.split("/")[-1])
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None
        else:
            message = None

        if message is not None:
            await message.reply(
                "https://tenor.com/view/pes-pesuniversity-pesu-may-the-pride-of-pes-may-the-pride-of-pes-be-with-you-gif-21274060"
            )
        else:
            await interaction.followup.send(
                "https://tenor.com/view/pes-pesuniversity-pesu-may-the-pride-of-pes-may-the-pride-of-pes-be-with-you-gif-21274060"
            )

    @pride.error
    async def pride_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandInvokeError):
            if isinstance(error.original, discord.NotFound):
                await interaction.followup.send(
                    "The specified message does not exist or is not in the channel",
                    ephemeral=True,
                )
            elif isinstance(error.original, discord.Forbidden):
                await interaction.followup.send(
                    "I do not have permission to reply to that message", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    embed=ug.build_unknown_error_embed(error)
                )
        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(
        name="ask", description="Ask a question regarding PESU"
    )
    @app_commands.describe(query="The question that needs to be answered")
    async def ask(self, interaction: discord.Interaction, query: str | None = None):
        await interaction.response.defer()
        url = "https://pesu-dev-askpesu.hf.space/ask"
        payload = {"query": query}
        try:
            async with httpx.AsyncClient(timeout=500) as client:
                resp = await client.post(url, json=payload)
                print(resp)
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data['answer']
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

                    first_embed = discord.Embed(
                        title=f"{query}",
                        description=chunks[0].strip(),
                        color=discord.Color.orange()
                    )
                    first_embed.set_footer(text="Powered by rowletLLM")
                    await interaction.edit_original_response(embed=first_embed)

                    for c in chunks[1:]:
                        embed = discord.Embed(
                            description=c.strip(),
                            color=discord.Color.orange()
                        )
                        embed.set_footer(text="Powered by rowletLLM")
                        await interaction.followup.send(embed=embed)

                else:
                    await interaction.edit_original_response(
                        content=f"Request failed with status {resp.status_code}."
                    )
        except Exception as e:
            await interaction.followup.send(e)

    @staticmethod
    async def fetch_data():
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        url = "https://reddit.com/r/PESU/comments/14c1iym/.json"

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                x = data[0]["data"]["children"][0]["data"]["selftext"]
                finedata = {}
                y = x.split("# ")
                for i in y:
                    j = i.split("\n\n")
                    if "This post will be" in j[0]:
                        continue
                    s = j[1].split("* ")
                    news = list(filter(None, s))
                    for i in news:
                        if ") or [" in i:
                            chakdeh = i.split(") or [")
                            for i in chakdeh:
                                l = i.split("](")
                                if l[0].startswith("["):
                                    l[0] = l[0][1:]
                                if l[1].endswith(")"):
                                    l[1] = l[1][:-1]
                                finedata.setdefault(j[0], []).append({l[0]: l[1]})
                        else:
                            chakdeh = i.split("](")
                            if chakdeh[0].startswith("["):
                                chakdeh[0] = chakdeh[0][1:]
                            if chakdeh[1].endswith(")"):
                                chakdeh[1] = chakdeh[1][:-1]
                            if chakdeh[1].endswith("\n"):
                                chakdeh[1] = chakdeh[1][:-1]
                            finedata.setdefault(j[0], []).append({chakdeh[0]: chakdeh[1]})
                return finedata
            else:
                resp = response.text
                print(
                    f"Failed to fetch data: {response.status_code}, falling back to local data. {resp}"
                )
                with open("faq.json", "r") as file:
                    data = json.load(file)
                return data
        
    async def get_data(self):
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
    ):
        data = await self.get_data()

        if category and category not in data:
            await interaction.response.send_message(
                f"Invalid category selected", ephemeral=True
            )
            return

        if question and not category:
            await interaction.response.send_message(
                "Please choose a category before selecting a question", ephemeral=True
            )
            return

        if category and not question:
            questions = []
            for entry in data[category]:
                for q in entry:
                    if entry[q].endswith(")") or q.endswith("\n"):
                        entry[q] = entry[q][:-1]
                    questions.append(f"[{q}]({entry[q]})")
            if questions:
                embed = discord.Embed(
                    title=f"FAQ - {category}",
                    description="\n\n".join(questions),
                    color=discord.Color.blurple(),
                )
                await interaction.response.send_message(embed=embed)

            else:
                embed = discord.Embed(
                    title="FAQ",
                    description="No questions found in this category",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if question and category:
            for entry in data[category]:
                if question in entry:
                    url = entry[question]
                    if url.endswith(")") or url.endswith("\n"):
                        url = url[:-1]
                    await interaction.response.send_message(
                        f"[{question}]({url})", ephemeral=False
                    )
                    return
            await interaction.response.send_message(
                "Question not found in the selected category", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "[Read the full FAQ](https://www.reddit.com/r/PESU/comments/14c1iym/faqs/)",
            ephemeral=False,
        )

    @faq.autocomplete("category")
    async def category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        data = await self.get_data()
        return [
            app_commands.Choice(name=cat, value=cat)
            for cat in data.keys()
            if current.lower() in cat.lower()
        ]

    @faq.autocomplete("question")
    async def question_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        data = await self.get_data()
        category = getattr(interaction.namespace, "category", None)

        if not category or category not in data:
            return [app_commands.Choice(name="⚠️ Select a category first", value="")]

        questions = []
        for entry in data[category]:
            for q in entry:
                if current.lower() in q.lower():
                    questions.append(q)

        return [
            app_commands.Choice(name=q[:100], value=q[:100]) for q in questions[:25]
        ]

    @faq.error
    async def faq_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="reload", description="Reload all cogs or a specific cog")
    @app_commands.describe(cog="The specific cog to reload (leave empty to reload all)")
    async def reload(
        self, interaction: discord.Interaction, cog: str | None = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        # Check if user has admin permission
        if not ug.has_bot_dev_permissions(interaction.user):
            await interaction.followup.send(
                content="You don't have permission to use this command.", ephemeral=True
            )
            return
            
        
        if cog:
            # Reload a specific cog
            try:
                await self.client.reload_extension(cog)
                self.client.logger.info(f"Reloaded cog: {cog}")
                await interaction.followup.send(
                    content=f"Successfully reloaded cog: `{cog}`", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    content=f"Failed to reload cog `{cog}`: {str(e)}", ephemeral=True
                )
        else:
            # Reload all cogs
            success = []
            failed = []
            
            # Unload all cogs first
            for path in Path("cogs").rglob("*.py"):
                if path.name.startswith("__"):
                    continue
                    
                cog_name = ".".join(path.with_suffix("").parts)
                try:
                    await self.client.unload_extension(cog_name)
                    self.client.logger.info(f"Unloaded cog: {cog_name}")
                except Exception:
                    # Ignore errors on unload
                    pass
            
            # Now load all cogs
            for path in Path("cogs").rglob("*.py"):
                if path.name.startswith("__"):
                    continue
                    
                cog_name = ".".join(path.with_suffix("").parts)
                try:
                    await self.client.load_extension(cog_name)
                    self.client.logger.info(f"Reloaded cog: {cog_name}")
                    success.append(cog_name)
                except Exception as e:
                    failed.append((cog_name, str(e)))
            
            # Create response message
            response = f"Reloaded {len(success)} cogs successfully."
            if failed:
                response += f"\nFailed to reload {len(failed)} cogs:"
                for cog_name, error in failed:
                    response += f"\n- `{cog_name}`: {error[:100]}{'...' if len(error) > 100 else ''}"
            
            await interaction.followup.send(content=response, ephemeral=True)

    @reload.error
    async def reload_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))


async def setup(client: DiscordBot):
    await client.add_cog(
        SlashUtils(client),
        guild=discord.Object(id=ug.load_config_value("GUILD", {}).get("ID")),
    )
