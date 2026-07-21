#!/usr/bin/env python3
"""Guild command registry utilities for local use and CI deploys.

Usage:
    uv run scripts/sync_guild_commands.py changed --base <old-sha> --head <new-sha>
    uv run scripts/sync_guild_commands.py sync
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


_SLASH_DECORATORS = frozenset({"app_commands.command", "commands.hybrid_command"})


def _is_app_commands_group_call(node: ast.Call) -> bool:
    return _decorator_path(node) == "app_commands.Group"


def _extract_groups_from_class(class_node: ast.ClassDef) -> dict[str, dict[str, str | None]]:
    groups: dict[str, dict[str, str | None]] = {}
    for stmt in class_node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if not isinstance(target, ast.Name):
                continue
            if not isinstance(stmt.value, ast.Call) or not _is_app_commands_group_call(stmt.value):
                continue
            parent_var: str | None = None
            for keyword in stmt.value.keywords:
                if keyword.arg == "parent" and isinstance(keyword.value, ast.Name):
                    parent_var = keyword.value.id
            groups[target.id] = {
                "name": _keyword_str(stmt.value, "name") or target.id,
                "parent_var": parent_var,
            }
    return groups


def _slash_command_key(decorator: ast.Call, func_name: str) -> str | None:
    if _decorator_path(decorator) not in _SLASH_DECORATORS:
        return None
    name = _keyword_str(decorator, "name") or func_name
    return f"slash:{name}"


def _named_groups_command_key(decorator: ast.Call, func_name: str) -> str | None:
    """Resolve @ModGroups.mod.command, @AnonGroups.anon.command, etc."""
    root = _decorator_root(decorator)
    if not isinstance(root, ast.Attribute) or root.attr != "command":
        return None
    group_attr = root.value
    if not isinstance(group_attr, ast.Attribute):
        return None
    if not isinstance(group_attr.value, ast.Name) or not group_attr.value.id.endswith("Groups"):
        return None

    group_paths: dict[tuple[str, str], tuple[str, ...]] = {
        ("ModGroups", "mod"): ("mod",),
        ("ModGroups", "mod_link"): ("mod", "link"),
        ("ModGroups", "mod_anon"): ("mod", "anon"),
        ("AnonGroups", "anon"): ("anon",),
        ("EngGroups", "eng"): ("eng",),
    }
    path = group_paths.get((group_attr.value.id, group_attr.attr))
    if path is None:
        return None

    cmd_name = _keyword_str(decorator, "name") or func_name
    return f"slash:{' '.join(path)} {cmd_name}"


def _group_command_key(
    decorator: ast.Call,
    func_name: str,
    groups: dict[str, dict[str, str | None]],
) -> str | None:
    root = _decorator_root(decorator)
    if not isinstance(root, ast.Attribute) or root.attr != "command":
        return None
    if not isinstance(root.value, ast.Name):
        return None
    group_var = root.value.id
    group_info = groups.get(group_var)
    if group_info is None:
        return None

    cmd_name = _keyword_str(decorator, "name") or func_name
    group_name = group_info["name"]
    parent_var = group_info["parent_var"]
    if parent_var and parent_var in groups:
        parent_name = groups[parent_var]["name"]
        return f"slash:{parent_name} {group_name} {cmd_name}"
    return f"slash:{group_name} {cmd_name}"


def _collect_command_keys(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    groups: dict[str, dict[str, str | None]],
    commands: set[str],
) -> None:
    for decorator in func_node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if key := _slash_command_key(decorator, func_node.name):
            commands.add(key)
        elif key := _group_command_key(decorator, func_node.name, groups):
            commands.add(key)
        elif key := _named_groups_command_key(decorator, func_node.name):
            commands.add(key)


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
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            groups = _extract_groups_from_class(node)
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    _collect_command_keys(item, groups, commands)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _collect_command_keys(node, {}, commands)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and (key := _context_menu_key(node)):
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
        if path.startswith(COGS_PREFIX)
        and path.endswith(".py")
        and not Path(path).name.startswith("__")
        and "/_" not in path.replace("\\", "/")
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
