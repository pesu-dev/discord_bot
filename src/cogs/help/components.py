from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from src.utils.general import build_embed

if TYPE_CHECKING:
    from src.bot import DiscordBot

# category -> (description, commands); pages are built by chunking commands
HELP_PAGES: dict[str, tuple[str, list[dict]]] = {
    "anon": (
        "Anon Commands",
        [{"name": "Send an Anon Message", "value": "`/anon send`"}],
    ),
    "eng": (
        "Engineering Commands",
        [
            {"name": "Ping", "value": "`/eng ping`"},
            {"name": "Uptime", "value": "`/eng uptime`"},
            {"name": "Support", "value": "`/eng support`"},
            {"name": "Reload Cogs", "value": "`/eng reload`"},
        ],
    ),
    "general": (
        "General Commands",
        [
            {"name": "User Info", "value": "`/info`"},
            {"name": "Count", "value": "`/count`"},
            {"name": "Spotify", "value": "`/spotify`"},
            {"name": "Toggle Role", "value": "`/togglerole`"},
            {"name": "Self Mute", "value": "`/selfmute`"},
            {"name": "Pride", "value": "`/pride`"},
            {"name": "FAQ", "value": "`/faq`"},
            {"name": "Ask PESU", "value": "`/ask`"},
        ],
    ),
    "mod": (
        "Mod Commands",
        [
            {"name": "Kick a User", "value": "`/mod kick`"},
            {"name": "Echo a Message", "value": "`/echo`"},
            {"name": "Link Info", "value": "`/mod link info`"},
            {"name": "Disconnect a User's Link", "value": "`/mod link disconnect`"},
            {"name": "Mute a User", "value": "`/mod mute`"},
            {"name": "Unmute a User", "value": "`/mod unmute`"},
            {"name": "Purge Messages", "value": "`/mod purge`"},
            {"name": "Lock a Channel", "value": "`/mod lock`"},
            {"name": "Unlock a Channel", "value": "`/mod unlock`"},
            {"name": "Timeout a User", "value": "`/mod timeout`"},
            {"name": "De-timeout a User", "value": "`/mod detimeout`"},
            {
                "name": "Ban a User from Anon",
                "value": "`/mod anon ban` — specify either `member` or `link`",
            },
            {"name": "Unban a User from Anon", "value": "`/mod anon unban`"},
            {
                "name": "Mute a User from Anon",
                "value": "`/mod anon mute` — specify either `member` or `link`",
            },
            {"name": "Unmute a User from Anon", "value": "`/mod anon unmute`"},
            {"name": "Anon Restriction Info", "value": "`/mod anon info`"},
        ],
    ),
}


class HelpEmbeds:
    def __init__(self, client: DiscordBot) -> None:
        welcome = client.config.get_channel("WELCOME")
        purple = discord.Color.dark_purple()

        self.unlink = [
            build_embed(
                title="PESU Bot",
                color=purple,
                description=f"Visit {welcome.mention} to get started, then link your account below.",
                fields=[{"name": "Link your Account", "value": "`/link <username> <password>`"}],
            ),
        ]

        self.pages: dict[str, list[discord.Embed]] = {
            category: [
                build_embed(title="PESU Bot", color=purple, description=description, fields=commands[i : i + 3])
                for i in range(0, len(commands), 3)
            ]
            for category, (description, commands) in HELP_PAGES.items()
        }


class HelpView(discord.ui.View):
    def __init__(
        self,
        interaction: discord.Interaction,
        client: DiscordBot,
        category: str = "anon",
        page: int = 0,
    ) -> None:
        super().__init__(timeout=60)
        self.interaction = interaction
        self.client = client
        self.category = category.lower()
        self.page = page
        self.message: discord.Message | None = None
        self.help_embeds = HelpEmbeds(client)
        self.embeds = self.help_embeds.pages.get(self.category, self.help_embeds.pages["anon"])
        self.update_buttons()

    def update_buttons(self) -> None:
        self.clear_items()
        self.add_item(HelpSelect(self))
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
    def __init__(self, view: HelpView) -> None:
        options = [
            discord.SelectOption(label="Anonymous Commands", value="anon", emoji="🖖"),
            discord.SelectOption(label="General Commands", value="general", emoji="⚙️"),
            discord.SelectOption(label="Engineering Commands", value="eng", emoji="🔧"),
            discord.SelectOption(label="Moderation Commands", value="mod", emoji="👮"),
        ]
        super().__init__(placeholder="Select category", options=options)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view_ref.category = self.values[0]
        self.view_ref.page = 0
        pages = self.view_ref.help_embeds.pages
        self.view_ref.embeds = pages.get(self.view_ref.category, pages["anon"])
        self.view_ref.update_buttons()
        await interaction.response.edit_message(embed=self.view_ref.get_embed(), view=self.view_ref)


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
