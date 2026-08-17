# Scripts

## `sync_guild_commands.py`

Detects when slash commands, groups, or context menus were added, removed, or had
Discord-facing surface changes (name, description, options/signature, related
decorators), and syncs the cog command tree to Discord.

```bash
# Compare two git refs (exit 0 = unchanged, exit 1 = surface changed)
uv run scripts/sync_guild_commands.py changed --base <old-sha> --head <new-sha>

# Push current commands to Discord (requires BOT_TOKEN)
uv run scripts/sync_guild_commands.py sync
```

Used by `.github/actions/sync-guild-commands` for development and production deploys.

## `next_semver.py`

Prints the next `MAJOR.MINOR.PATCH` version by bumping the latest git tag that
matches exact `vMAJOR.MINOR.PATCH` (prerelease / junk `v*` tags are skipped).
Pass `--merged COMMIT` to ignore tags that are not ancestors of that commit.
Used by the production promote workflow.

```bash
python3 scripts/next_semver.py --bump patch
python3 scripts/next_semver.py --bump minor --merged HEAD
python3 scripts/next_semver.py --bump major
```

## `check_cog_imports.py`

Imports every discovered cog package to catch circular imports and broken package
layout. Used by CI package checks and local quality gates.

```bash
uv run scripts/check_cog_imports.py
```

## `post_welcome_and_rules.py`

One-off helper to post (or dry-run preview) the Welcome and Rules/Roles embeds to
configured Discord channels. Requires `BOT_TOKEN` (via `src/.env` or the environment).

```bash
# Preview both payloads in a channel
uv run scripts/post_welcome_and_rules.py --channel-id 123456789012345678

# Real send to welcome + rules-and-info
uv run scripts/post_welcome_and_rules.py --no-dry-run
```
