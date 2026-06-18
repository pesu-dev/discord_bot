#!/usr/bin/env python3
"""Guild command registry utilities for local use and CI deploys.

Usage:
    uv run python scripts/sync_guild_commands.py changed --base <old-sha> --head <new-sha>
    uv run python scripts/sync_guild_commands.py sync
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COGS_PREFIX = "src/cogs/"

sys.path.insert(0, str(REPO_ROOT))


def _decorator_root(decorator: ast.expr) -> ast.expr:
    node = decorator
    while isinstance(node, ast.Call):
        node = node.func
    return node


def _decorator_path(node: ast.expr) -> str | None:
    root = _decorator_root(node)
    if isinstance(root, ast.Attribute):
        parts: list[str] = []
        current: ast.expr = root
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    if isinstance(root, ast.Name):
        return root.id
    return None


def _keyword_str(node: ast.Call, key: str) -> str | None:
    for keyword in node.keywords:
        if keyword.arg != key:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _call_root_name(node: ast.Call) -> str | None:
    root = node.func
    if isinstance(root, ast.Attribute):
        return root.attr
    if isinstance(root, ast.Name):
        return root.id
    return None


_SLASH_DECORATORS = frozenset({"app_commands.command", "commands.command", "commands.hybrid_command"})


def _slash_command_key(decorator: ast.Call, func_name: str) -> str | None:
    if _decorator_path(decorator) not in _SLASH_DECORATORS:
        return None
    name = _keyword_str(decorator, "name") or func_name
    return f"slash:{name}"


def _context_menu_key(node: ast.Assign) -> str | None:
    if not isinstance(node.value, ast.Call) or _call_root_name(node.value) != "ContextMenu":
        return None
    name = _keyword_str(node.value, "name")
    return f"context_menu:{name}" if name else None


def extract_commands_from_source(source: str, *, filename: str = "<unknown>") -> set[str]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return set()

    commands: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and (key := _slash_command_key(decorator, node.name)):
                    commands.add(key)
        elif isinstance(node, ast.Assign) and (key := _context_menu_key(node)):
            commands.add(key)

    return commands


def list_cog_files_at_ref(ref: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", "src/cogs"],
        cwd=REPO_ROOT,
        text=True,
    )
    return [
        path
        for path in output.splitlines()
        if path.startswith(COGS_PREFIX) and path.endswith(".py") and not Path(path).name.startswith("__")
    ]


def extract_commands_at_ref(ref: str) -> frozenset[str]:
    commands: set[str] = set()
    for path in list_cog_files_at_ref(ref):
        source = subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=REPO_ROOT, text=True)
        commands.update(extract_commands_from_source(source, filename=path))
    return frozenset(commands)


def format_command_changes(added: set[str], removed: set[str]) -> str:
    lines: list[str] = []
    for key in sorted(added):
        lines.append(f"  + {key}")
    for key in sorted(removed):
        lines.append(f"  - {key}")
    return "\n".join(lines)


def run_changed(base: str, head: str) -> int:
    try:
        base_commands = extract_commands_at_ref(base)
        head_commands = extract_commands_at_ref(head)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to read git refs: {exc}", file=sys.stderr)
        return 2

    added = head_commands - base_commands
    removed = base_commands - head_commands
    if not added and not removed:
        print(f"No command additions or deletions between {base} and {head}.")
        print(f"Command count unchanged at {len(head_commands)}.")
        return 0

    print(f"Command registry changed between {base} and {head}:")
    print(format_command_changes(added, removed))
    return 1


async def _sync_guild_commands() -> None:
    from dotenv import load_dotenv

    from src.bot import DiscordBot

    load_dotenv(REPO_ROOT / "src" / ".env")

    token = os.getenv("BOT_TOKEN")
    if not token:
        msg = "BOT_TOKEN is not set"
        raise RuntimeError(msg)

    bot = DiscordBot()
    await bot.login(token)
    try:
        guild = bot.config.guild_object
        await bot.tree.sync(guild=guild)
        bot.logger.info("Synced all commands to the guild")
        bot.logger.info("Guild command sync finished")
    finally:
        await bot.close()


def run_sync() -> int:
    try:
        asyncio.run(_sync_guild_commands())
    except Exception as exc:
        print(f"Command sync failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guild command registry utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    changed_parser = subparsers.add_parser(
        "changed",
        help="Exit 1 if slash commands or context menus were added or removed between two git refs.",
    )
    changed_parser.add_argument("--base", required=True, help="Base git ref (previously deployed commit)")
    changed_parser.add_argument("--head", required=True, help="Head git ref (commit being deployed)")

    subparsers.add_parser(
        "sync",
        help="Load cogs and sync guild commands to Discord (requires BOT_TOKEN and APP_ENV).",
    )

    args = parser.parse_args(argv)

    if args.command == "changed":
        return run_changed(args.base, args.head)
    if args.command == "sync":
        return run_sync()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
