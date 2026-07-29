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
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))


def _dotted_name(node: ast.expr) -> str | None:
    """`app_commands.command` / `ModGroups.mod.command` → dotted string."""
    parts: list[str] = []
    cur: ast.expr = node
    while isinstance(cur, ast.Call):
        cur = cur.func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _kw_str(call: ast.Call, key: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _hash_nodes(*nodes: ast.AST) -> str:
    payload = "\0".join(ast.dump(n, annotate_fields=True) for n in nodes)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _is_command_decorator(node: ast.expr) -> bool:
    name = _dotted_name(node)
    return bool(name and (name.endswith(".command") or name.endswith("hybrid_command")))


def _call_basename(call: ast.Call) -> str | None:
    name = _dotted_name(call)
    return name.rsplit(".", 1)[-1] if name else None


def _add_command(
    surfaces: dict[str, str],
    filename: str,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    qual: str,
) -> None:
    if any(_is_command_decorator(d) for d in func.decorator_list):
        surfaces[f"{filename}:{qual}"] = _hash_nodes(*func.decorator_list, func.args)


def _add_registry_call(surfaces: dict[str, str], filename: str, call: ast.Call) -> None:
    kind = _call_basename(call)
    if kind not in {"Group", "ContextMenu"}:
        return
    label = _kw_str(call, "name")
    if not label:
        return
    prefix = "group" if kind == "Group" else "context_menu"
    surfaces[f"{filename}:{prefix}:{label}"] = _hash_nodes(call)


def _collect_class(surfaces: dict[str, str], filename: str, node: ast.ClassDef) -> None:
    for item in node.body:
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            _add_command(surfaces, filename, item, f"{node.name}.{item.name}")
        elif isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
            _add_registry_call(surfaces, filename, item.value)


def extract_surfaces(source: str, *, filename: str = "<unknown>") -> dict[str, str]:
    """Map stable keys → hashes of Discord-facing AST (decorators + signature, not bodies)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return {}

    surfaces: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            _collect_class(surfaces, filename, node)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _add_command(surfaces, filename, node, node.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            _add_registry_call(surfaces, filename, node.value)

    # ContextMenu constructed inside methods (e.g. self.ctx_menu = ContextMenu(...)).
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _call_basename(node.value) == "ContextMenu":
                _add_registry_call(surfaces, filename, node.value)

    return surfaces


def cog_files_at_ref(ref: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", "src/cogs"],
        cwd=REPO_ROOT,
        text=True,
    )
    files: list[str] = []
    for path in output.splitlines():
        if not path.endswith(".py"):
            continue
        name = Path(path).name
        # Keep __init__.py (context menus live there); skip other private modules.
        if name.startswith("_") and name != "__init__.py":
            continue
        files.append(path)
    return files


def surfaces_at_ref(ref: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in cog_files_at_ref(ref):
        source = subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=REPO_ROOT, text=True)
        out.update(extract_surfaces(source, filename=path))
    return out


def run_changed(base: str, head: str) -> int:
    try:
        before = surfaces_at_ref(base)
        after = surfaces_at_ref(head)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to read git refs: {exc}", file=sys.stderr)
        return 2

    before_keys, after_keys = set(before), set(after)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    modified = sorted(k for k in before_keys & after_keys if before[k] != after[k])

    if not added and not removed and not modified:
        print(f"No command surface changes between {base} and {head}.")
        print(f"Surface count unchanged at {len(after)}.")
        return 0

    print(f"Command registry changed between {base} and {head}:")
    for key in added:
        print(f"  + {key}")
    for key in removed:
        print(f"  - {key}")
    for key in modified:
        print(f"  ~ {key}")
    return 1


async def _sync_guild_commands() -> None:
    from dotenv import load_dotenv

    from src.bot import DiscordBot

    load_dotenv(REPO_ROOT / "src" / ".env")
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    bot = DiscordBot()
    await bot.login(token)
    try:
        await bot.tree.sync(guild=bot.config.guild_object)
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
    sub = parser.add_subparsers(dest="command", required=True)

    changed = sub.add_parser(
        "changed",
        help="Exit 1 if Discord-facing command surfaces changed between two git refs.",
    )
    changed.add_argument("--base", required=True, help="Base git ref (previously deployed commit)")
    changed.add_argument("--head", required=True, help="Head git ref (commit being deployed)")
    sub.add_parser("sync", help="Sync guild commands to Discord (requires BOT_TOKEN and APP_ENV).")

    args = parser.parse_args(argv)
    if args.command == "changed":
        return run_changed(args.base, args.head)
    if args.command == "sync":
        return run_sync()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
