#!/usr/bin/env python3
"""One-off script to post Welcome and Rules/Roles embeds.

Usage:
    # Preview both payloads in a channel
    uv run scripts/post_welcome_and_rules.py --channel-id 123456789012345678

    # Real send to welcome + rules-and-info
    uv run scripts/post_welcome_and_rules.py --no-dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.utils.config import Config  # noqa: E402
from src.utils.general import build_embed  # noqa: E402

WELCOME_ID = 742946580285620225
RULES_AND_INFO_ID = 932541238589128764
ACCESS_HELP_ID = 742956204753551440
NUTTY_NUTTY_ID = 778655633095786507

ADMIN_ROLE = Config.ROLES["ADMIN"]
MOD_ROLE = Config.ROLES["MOD"]
JUNIOR_MOD_ROLE = Config.ROLES["JUNIOR_MOD"]
BOOSTER_ROLE = 752150613998960710
LEVEL_ROLES = (
    1518781674127888434,
    1518781648731111504,
    818139400197636126,
    867819873148338206,
    1023347804162232461,
)
GAMER_ROLE = 778825985361051660
CODER_ROLE = 778875127257104424
MUSICIAN_ROLE = 778875199701385216
EDITOR_ROLE = 782642024071168011
TECH_ROLE = 790106229997174786
MOTO_ROLE = 836652197214421012
INVESTORS_ROLE = 936886064361144360
PESU_DEV_ROLE = 810507351063920671
NSFW_ROLE = 778820724424704011

INVITE_URL = "https://discord.gg/eZ3uFs2"
WELCOME_COLOR = discord.Color.green()
EMBED_COLOR = discord.Color.blurple()


def _role_mentions(*role_ids: int) -> str:
    return " ".join(f"<@&{role_id}>" for role_id in role_ids)


def _welcome_embed(*, thumbnail: str | None = None) -> discord.Embed:
    return build_embed(
        title="Welcome",
        color=WELCOME_COLOR,
        description=(
            "Welcome to PESU Discord.\n\n"
            f"Go through <#{RULES_AND_INFO_ID}> and follow the rules at all times on this server.\n\n"
            "For access to the rest of the server, run `/link` with your PESU Academy username and password.\n\n"
            f"If you need help linking or getting access, drop a message in <#{ACCESS_HELP_ID}>. Have fun!\n\n"
            f"Invite fellow PESU people onto this server by sending them this invite link: {INVITE_URL}"
        ),
        thumbnail=thumbnail,
    )


def _roles_embed() -> discord.Embed:
    optional = _role_mentions(
        GAMER_ROLE,
        CODER_ROLE,
        MUSICIAN_ROLE,
        EDITOR_ROLE,
        TECH_ROLE,
        MOTO_ROLE,
        INVESTORS_ROLE,
    )
    return build_embed(
        title="Roles",
        color=EMBED_COLOR,
        description=(
            f"<@&{ADMIN_ROLE}> — Server Admin. Their decisions are final.\n\n"
            f"<@&{MOD_ROLE}> — Server Moderators. They're here to help and keep things in order. "
            "Their decisions are final as well.\n\n"
            f"<@&{JUNIOR_MOD_ROLE}> — Junior Moderators. They help moderate and support the community.\n\n"
            f"<@&{BOOSTER_ROLE}> — Server boosters. Thanks for keeping the lights on!\n\n"
            f"**Leveling:** {_role_mentions(*LEVEL_ROLES)}\n\n"
            f"<@&{PESU_DEV_ROLE}> — PESU Dev engineers working on bots and server tooling.\n\n"
            f"**Optional roles:** Pick up extras with `/togglerole`: {optional}.\n"
            f"Grab <@&{NSFW_ROLE}> the same way to unlock <#{NUTTY_NUTTY_ID}>."
        ),
    )


def _rules_embed() -> discord.Embed:
    return build_embed(
        title="Rules",
        color=EMBED_COLOR,
        description=(
            "1. Be respectful, civil, and welcoming.\n"
            "2. Discriminatory language and hate speech are forbidden.\n"
            "3. Leaking anyone's personal information (doxxing) is strictly prohibited.\n"
            f"4. No inappropriate or unsafe content outside NSFW spaces. NSFW belongs in "
            f"<#{NUTTY_NUTTY_ID}> — grab <@&{NSFW_ROLE}> with `/togglerole` for access.\n"
            "5. Alternate accounts are not allowed under any circumstances.\n"
            "6. Catfishing and fake identities are forbidden.\n"
            "7. Do not share or link scam websites or phishing content.\n"
            "8. Spoilers must use spoiler tags and be labeled.\n"
            "9. Ghost pings are taken seriously and can earn a minimum 1-day mute.\n"
            f"10. Need staff help? Ping an online <@&{ADMIN_ROLE}>, <@&{MOD_ROLE}>, or "
            f"<@&{JUNIOR_MOD_ROLE}>. Unnecessary staff pings can earn a minimum 1-day mute.\n"
            "11. Keep conversation aligned with the channel name and description.\n"
            "12. Follow the Discord Terms of Service.\n"
            "13. No spam, flooding, or unsolicited self-promo.\n"
            "14. Staff decisions are final."
        ),
    )


async def _guild_icon_url(client: discord.Client) -> str | None:
    guild = await client.fetch_guild(Config.GUILD_ID)
    return guild.icon.url if guild.icon is not None else None


async def _require_text_channel(client: discord.Client, channel_id: int) -> discord.TextChannel:
    channel = await client.fetch_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        msg = f"Channel {channel_id} is not a text channel"
        raise TypeError(msg)
    return channel


async def _post(*, preview_channel_id: int | None) -> None:
    load_dotenv(REPO_ROOT / "src" / ".env")
    token = os.getenv("BOT_TOKEN")
    if not token:
        msg = "BOT_TOKEN is not set"
        raise RuntimeError(msg)

    dry_run = preview_channel_id is not None
    mode = "DRY-RUN" if dry_run else "LIVE"
    client = discord.Client(intents=discord.Intents.default())
    await client.login(token)
    try:
        print(f"[{mode}] Logged in as {client.user}")
        icon_url = await _guild_icon_url(client)
        if icon_url is None:
            print(f"[{mode}] Warning: guild has no icon; welcome embed will omit thumbnail")
        welcome_embed = _welcome_embed(thumbnail=icon_url)
        roles_embed = _roles_embed()
        rules_embed = _rules_embed()

        if dry_run:
            assert preview_channel_id is not None
            preview = await _require_text_channel(client, preview_channel_id)
            welcome_msg = await preview.send(content="**[DRY-RUN] Welcome preview**", embed=welcome_embed)
            rules_msg = await preview.send(
                content="**[DRY-RUN] Rules & roles preview**",
                embeds=[roles_embed, rules_embed],
            )
            print(f"[{mode}] Preview welcome -> #{preview.name} ({welcome_msg.id})")
            print(f"[{mode}] Preview roles+rules -> #{preview.name} ({rules_msg.id})")
        else:
            welcome_channel = await _require_text_channel(client, WELCOME_ID)
            rules_channel = await _require_text_channel(client, RULES_AND_INFO_ID)
            welcome_msg = await welcome_channel.send(embed=welcome_embed)
            roles_msg = await rules_channel.send(embed=roles_embed)
            rules_msg = await rules_channel.send(embed=rules_embed)
            print(f"[{mode}] Welcome -> #{welcome_channel.name} ({welcome_msg.id})")
            print(f"[{mode}] Roles -> #{rules_channel.name} ({roles_msg.id})")
            print(f"[{mode}] Rules -> #{rules_channel.name} ({rules_msg.id})")
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post Welcome and Rules/Roles embeds.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--channel-id",
        type=int,
        dest="channel_id",
        help="Preview channel ID (dry-run).",
    )
    mode.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Send to the real welcome and rules-and-info channels.",
    )
    args = parser.parse_args(argv)
    preview_channel_id = None if args.no_dry_run else args.channel_id

    try:
        asyncio.run(_post(preview_channel_id=preview_channel_id))
    except Exception as exc:
        print(f"Failed to post embeds: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
