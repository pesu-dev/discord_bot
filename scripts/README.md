# Scripts

## `sync_guild_commands.py`

Detects when slash commands, groups, or context menus were added, removed, or had
Discord-facing surface changes (name, description, options/signature, related
decorators), and syncs the cog command tree to Discord.

```bash
# Compare two git refs (exit 0 = unchanged, exit 1 = surface changed)
uv run scripts/sync_guild_commands.py changed --base <old-sha> --head <new-sha>

# Push current commands to Discord (requires BOT_TOKEN and APP_ENV)
uv run scripts/sync_guild_commands.py sync
```

Used by `.github/actions/sync-guild-commands` during dev and prod deploys.
