from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from src.bot import DiscordBot


class HelpEmbeds:
    def __init__(self, client: DiscordBot) -> None:
        welcome = client.config.get_channel("WELCOME")
        self.unlink = [
            discord.Embed(
                title="PESU Bot",
                description=f"Visit {welcome.mention} to get started, then link your account below.",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            ).add_field(name="Link your Account", value="`/link`", inline=False),
        ]

        self.anon = [
            discord.Embed(
                title="PESU Bot",
                description="Anon Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Send an Anon Message", value="`/anon send`", inline=False)
            .add_field(
                name="Ban a User",
                value="`/anon ban` — specify either `member` or `link`",
                inline=False,
            ),
            discord.Embed(
                title="PESU Bot",
                description="Anon Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Unban a User", value="`/anon unban-user`", inline=False)
            .add_field(name="Get Ban Info of a User", value="`/anon ban-info`", inline=False),
        ]

        self.eng = [
            discord.Embed(
                title="PESU Bot",
                description="Engineering Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Ping", value="`/eng ping`", inline=False)
            .add_field(name="Uptime", value="`/eng uptime`", inline=False)
            .add_field(name="Support", value="`/eng support`", inline=False)
            .add_field(name="Reload Cogs", value="`/eng reload`", inline=False),
        ]

        self.utils = [
            discord.Embed(
                title="PESU Bot",
                description="Utility Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Link your Account", value="`/link`", inline=False)
            .add_field(name="User Info", value="`/info`", inline=False),
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
            .add_field(name="FAQ", value="`/faq`", inline=False)
            .add_field(name="Ask PESU", value="`/ask`", inline=False),
        ]

        self.mod = [
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Kick a User", value="`/mod kick`", inline=False)
            .add_field(name="Echo a Message", value="`/echo`", inline=False)
            .add_field(name="Link Info", value="`/mod link info`", inline=False)
            .add_field(name="Disconnect a User's Link", value="`/mod link disconnect`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Mute a User", value="`/mod mute`", inline=False)
            .add_field(name="Unmute a User", value="`/mod unmute`", inline=False)
            .add_field(name="Purge Messages", value="`/mod purge`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            )
            .add_field(name="Lock a Channel", value="`/mod lock`", inline=False)
            .add_field(name="Unlock a Channel", value="`/mod unlock`", inline=False)
            .add_field(name="Timeout a User", value="`/mod timeout`", inline=False),
            discord.Embed(
                title="PESU Bot",
                description="Mod Commands",
                color=discord.Color.dark_purple(),
                timestamp=discord.utils.utcnow(),
            ).add_field(name="De-timeout a User", value="`/mod detimeout`", inline=False),
        ]

    def get_embeds(self, category: str) -> list[discord.Embed]:
        return getattr(self, category.lower(), self.anon)


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
        self.embeds = HelpEmbeds(client).get_embeds(self.category)
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
            discord.SelectOption(label="Utility Commands", value="utils", emoji="⚙️"),
            discord.SelectOption(label="Engineering Commands", value="eng", emoji="🔧"),
            discord.SelectOption(label="Moderation Commands", value="mod", emoji="👮"),
        ]
        super().__init__(placeholder="Select category", options=options)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view_ref.category = self.values[0]
        self.view_ref.page = 0
        self.view_ref.embeds = HelpEmbeds(self.view_ref.client).get_embeds(self.view_ref.category)
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


def _has_linked_role(member: discord.Member, client: DiscordBot) -> bool:
    return any(role.id == client.config.linked_role.id for role in member.roles)



