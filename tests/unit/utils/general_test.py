from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.utils.general import (
    DM_AUTO_GENERATED_NOTICE,
    build_embed,
    build_unknown_error_embed,
    discover_cog_extensions,
    handle_command_error,
    mod_target_error,
    parse_time,
    resolve_cog_extension,
    send_dm_safely,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import MemberFactory


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10s", 10),
        ("5m", 300),
        ("2h", 7200),
        ("1d", 86400),
        ("1y", 31_536_000),
        ("42", 42),
        (" 3H ", 10_800),
    ],
)
def test_parse_time_valid(raw: str, expected: int) -> None:
    assert parse_time(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "1x", ""])
def test_parse_time_invalid(raw: str) -> None:
    with pytest.raises(ValueError, match="Invalid time format"):
        parse_time(raw)


def test_build_embed_fields_and_thumbnail() -> None:
    embed = build_embed(
        title="Hello",
        description="World",
        color=discord.Color.red(),
        fields=[{"name": "A", "value": "B", "inline": True}],
        footer="footer",
        thumbnail="https://example.com/t.png",
    )
    assert embed.title == "Hello"
    assert embed.description == "World"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "A"
    assert embed.footer.text == "footer"
    assert embed.thumbnail.url == "https://example.com/t.png"


def test_build_unknown_error_embed() -> None:
    embed = build_unknown_error_embed(RuntimeError("boom"))
    assert "Unexpected Error" in (embed.title or "")
    assert any(f.name == "Error Type" and f.value == "RuntimeError" for f in embed.fields)


async def test_send_dm_safely_embed_only_adds_notice_embed() -> None:
    user = MagicMock()
    user.send = AsyncMock()
    embed = build_embed(title="x", description="body", footer="keep me")
    assert await send_dm_safely(user, embed) is True
    assert user.send.await_args.kwargs["content"] is None
    sent_embeds = user.send.await_args.kwargs["embeds"]
    assert sent_embeds[0] is embed
    assert sent_embeds[0].description == "body"
    assert sent_embeds[0].footer.text == "keep me"
    assert sent_embeds[1].description == DM_AUTO_GENERATED_NOTICE


async def test_send_dm_safely_content_only_adds_notice_embed() -> None:
    user = MagicMock()
    user.send = AsyncMock()
    assert await send_dm_safely(user, content="hello") is True
    sent_embeds = user.send.await_args.kwargs["embeds"]
    assert user.send.await_args.kwargs["content"] == "hello"
    assert len(sent_embeds) == 1
    assert sent_embeds[0].description == DM_AUTO_GENERATED_NOTICE


async def test_send_dm_safely_content_and_embed_sends_two_embeds() -> None:
    user = MagicMock()
    user.send = AsyncMock()
    embed = build_embed(title="x", description="body")
    assert await send_dm_safely(user, embed, content="hello") is True
    sent_embeds = user.send.await_args.kwargs["embeds"]
    assert user.send.await_args.kwargs["content"] == "hello"
    assert sent_embeds[0] is embed
    assert sent_embeds[1].description == DM_AUTO_GENERATED_NOTICE


async def test_send_dm_safely_requires_payload() -> None:
    with pytest.raises(ValueError, match="embed and/or content"):
        await send_dm_safely(MagicMock())


async def test_send_dm_safely_forbidden() -> None:
    user = MagicMock()
    user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))
    assert await send_dm_safely(user, build_embed(title="x")) is False


async def test_handle_command_error_not_found() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    await handle_command_error(interaction, discord.NotFound(MagicMock(), "missing"), not_found="gone")
    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.kwargs["content"] == "gone"


async def test_handle_command_error_unknown_uses_embed() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    await handle_command_error(interaction, RuntimeError("nope"))
    kwargs = interaction.followup.send.await_args.kwargs
    assert "embed" in kwargs


def test_mod_target_error_bot(fake_config: MagicMock, member_factory: MemberFactory) -> None:
    member = member_factory(bot=True)
    assert mod_target_error(member, fake_config) is not None


def test_mod_target_error_admin(fake_config: MagicMock, member_factory: MemberFactory) -> None:
    member = member_factory(roles=[fake_config.admin_role])
    assert "admin/mod" in (mod_target_error(member, fake_config) or "").lower()


def test_mod_target_error_junior_mod(fake_config: MagicMock, member_factory: MemberFactory) -> None:
    member = member_factory(roles=[fake_config.junior_mod_role])
    assert "admin/mod" in (mod_target_error(member, fake_config) or "").lower()


def test_mod_target_error_allow_mod(fake_config: MagicMock, member_factory: MemberFactory) -> None:
    member = member_factory(roles=[fake_config.mod_role])
    assert mod_target_error(member, fake_config, allow_mod_target=True) is None


def test_mod_target_error_ok(fake_config: MagicMock, member_factory: MemberFactory) -> None:
    member = member_factory()
    assert mod_target_error(member, fake_config) is None


def test_discover_and_resolve_cogs(tmp_path: Path) -> None:
    cog = tmp_path / "demo"
    cog.mkdir()
    (cog / "__init__.py").write_text("# demo\n")
    (tmp_path / "_skip").mkdir()
    (tmp_path / "not_a_package").mkdir()

    found = discover_cog_extensions(tmp_path, package="pkg.cogs")
    assert found == ["pkg.cogs.demo"]
    assert resolve_cog_extension("demo", package="pkg.cogs", cogs_dir=tmp_path) == "pkg.cogs.demo"
    assert resolve_cog_extension("pkg.cogs.demo", package="pkg.cogs", cogs_dir=tmp_path) == "pkg.cogs.demo"
    with pytest.raises(ValueError, match="Unknown cog"):
        resolve_cog_extension("missing", package="pkg.cogs", cogs_dir=tmp_path)


def test_discover_real_cogs() -> None:
    extensions = discover_cog_extensions()
    assert "src.cogs.mod" in extensions
    assert "src.cogs.events" in extensions


async def test_handle_command_error_via_context() -> None:
    from discord.ext import commands

    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    await handle_command_error(ctx, discord.Forbidden(MagicMock(), "no"), forbidden="denied")
    ctx.send.assert_awaited_once()
    assert ctx.send.await_args.kwargs["content"] == "denied"

    await handle_command_error(ctx, RuntimeError("x"))
    assert "embed" in ctx.send.await_args.kwargs
