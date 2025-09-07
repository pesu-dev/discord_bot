import discord
from discord import app_commands
from discord.ext import commands

import utils.general as ug
from bot import DiscordBot


class HelpEmbeds:
    def __init__(self) -> None:
        self.anon = [
            discord.Embed(
                title="PESU Bot",
                description="Anon Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Send an Anon Message", value="`/anon`", inline=False)
            .add_field(name="Ban User from an Anon Message", value="`/bananon`", inline=False)
            .add_field(name="Ban a User", value="`/userbananon`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Anon Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Unban a User", value="`/userunbananon`", inline=False)
            .add_field(name="Get Ban Info of a User", value="`/anonbaninfo`", inline=False),
        ]

        self.utils = [
            discord.Embed(
                title="PESU Bot",
                description="Utility Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Ping", value="`/ping`", inline=False)
            .add_field(name="Uptime", value="`/uptime`", inline=False)
            .add_field(name="Support", value="`/support`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Utility Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Count", value="`/count`", inline=False)
            .add_field(name="Spotify", value="`/spotify`", inline=False)
            .add_field(name="Add Roles", value="`/addroles`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Utility Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Pride", value="`/pride`", inline=False)
            .add_field(name="FAQ", value="`/faq`", inline=False),
        ]

        self.mod = [
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Kick a User", value="`/kick`", inline=False)
            .add_field(name="Echo a Message", value="`/echo`", inline=False)
            .add_field(name="Change User's nick", value="`/changenick`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Mute a User", value="`/mute`", inline=False)
            .add_field(name="Unmute a User", value="`/unmute`", inline=False)
            .add_field(name="Purge Messages", value="`/purge`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Lock a Channel", value="`/lock`", inline=False)
            .add_field(name="Unlock a Channel", value="`/unlock`", inline=False)
            .add_field(name="Timeout a User", value="`/timeout`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            ).add_field(name="De-timeout a User", value="`/detimeout`", inline=False),
        ]

        self.link = [
            discord.Embed(
                title="PESU Bot",
                description="Link Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Get Info about a User", value="`/info`", inline=False)
            .add_field(name="De-link a User", value="`/delink`", inline=False)
        ]

    def get_embeds(self, category: str) -> list[discord.Embed]:
        return getattr(self, category.lower(), self.anon)


class HelpView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, category: str = "anon", page: int = 0) -> None:
        super().__init__(timeout=60)
        self.interaction = interaction
        self.category = category.lower()
        self.page = page
        self.message: discord.Message | None = None
        self.embeds = HelpEmbeds().get_embeds(self.category)
        self.update_buttons()

    def update_buttons(self) -> None:
        self.clear_items()
        self.add_item(HelpSelect(self.category))
        self.add_item(PrevButton(self))
        self.add_item(NextButton(self))

    def get_embed(self) -> discord.Embed:
        embed = self.embeds[self.page]
        total_pages = len(self.embeds)
        embed.set_footer(text=f"PESU Bot | Page {self.page + 1}/{total_pages}")
        return embed

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button | discord.ui.Select):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass


class HelpSelect(discord.ui.Select):
    def __init__(self, current_category: str) -> None:
        options = [
            discord.SelectOption(label="Anonymous Commands", value="anon", emoji="🖖"),
            discord.SelectOption(label="Utility Commands", value="utils", emoji="⚙️"),
            discord.SelectOption(label="Moderation Commands", value="mod", emoji="👮"),
            discord.SelectOption(label="Link Commands", value="link", emoji="🔗"),
        ]
        super().__init__(placeholder="Select category", options=options)
        self.current_category = current_category

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, HelpView):
            return

        self.view.category = self.values[0]
        self.view.page = 0
        self.view.embeds = HelpEmbeds().get_embeds(self.view.category)
        self.view.update_buttons()
        await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)


class PrevButton(discord.ui.Button):
    def __init__(self, view: HelpView) -> None:
        super().__init__(emoji="⬅️", style=discord.ButtonStyle.primary)
        self.view_ref = view
        self.disabled = view.page == 0

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view_ref.page > 0:
            self.view_ref.page -= 1
            self.view_ref.update_buttons()
            await interaction.response.edit_message(embed=self.view_ref.get_embed(), view=self.view_ref)


class NextButton(discord.ui.Button):
    def __init__(self, view: HelpView) -> None:
        super().__init__(emoji="➡️", style=discord.ButtonStyle.primary)
        self.view_ref = view
        self.disabled = view.page >= len(view.embeds) - 1

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view_ref.page < len(self.view_ref.embeds) - 1:
            self.view_ref.page += 1
            self.view_ref.update_buttons()
            await interaction.response.edit_message(embed=self.view_ref.get_embed(), view=self.view_ref)


class SlashHelp(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

    @app_commands.command(name="help", description="Show the bot's help menu")
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        if not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        if any(role.id == self.client.config.just_joined_role.id for role in interaction.user.roles):
            embed = discord.Embed(
                title="PESU Bot",
                description=f"Visit {self.client.config.get_channel('WELCOME').mention} to link first!",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="PESU Bot")
            embed.timestamp = discord.utils.utcnow()
            await interaction.followup.send(embed=embed)
            return

        view = HelpView(interaction, category="anon", page=0)
        message = await interaction.followup.send(embed=view.get_embed(), view=view)
        view.message = message

    @help_command.error
    async def help_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashHelp(client),
        guild=client.config.guild,
    )
