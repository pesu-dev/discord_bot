# AGENTS.md

Guidance for AI coding agents working in this repository.

> **Source of truth**: Keep agent instructions in this file (and nested `AGENTS.md` files if added later). Do not scatter the same guidance into `CLAUDE.md` or `.cursor/rules/` unless a tool-specific feature requires it.

## Stack

- Python **>=3.13**, package manager **uv** (never pip/poetry/npm-style installs)
- discord.py **2.7.x**, MongoDB via **pymongo**, HTTP via **httpx**
- Lint/format: **Ruff** (see `[tool.ruff]` in `pyproject.toml`)

## Commands

```bash
# Setup
.githooks/install.sh
uv sync --extra dev

# Run the bot (from repo root; requires src/.env)
uv run -m src

# Quality gates (match CI)
uv run ruff check .
uv run ruff format . --check
uv run -m compileall -q .
uv run scripts/check_cog_imports.py

# Auto-fix style
uv run ruff check . --fix
uv run ruff format .
```

Use `uv run …` for all Python tooling. Prefer `uv sync --frozen` only when matching CI lockfile installs.

## Layout

| Path                 | Purpose                                               |
| -------------------- | ----------------------------------------------------- |
| `src/bot.py`         | `DiscordBot` subclass, cog loading                    |
| `src/cogs/<name>/`   | One package per cog (auto-discovered)                 |
| `src/utils/`         | Shared config, decorators, helpers                    |
| `src/data/`          | Static data (e.g. `faq.json`)                         |
| `scripts/`           | CI/ops scripts (cog import check, guild command sync) |
| `deploy/`            | Compose + deploy helpers                              |
| `.github/workflows/` | CI/CD                                                 |

Human docs: `README.md`, `.github/CONTRIBUTING.md`. Prefer those for long setup detail; keep this file operational.

## Cog conventions

Each cog is `src/cogs/<name>/` with role-based files:

- `__init__.py` — `Slash*` cog class (mixins + `Cog`), lifecycle, `setup()`
- `groups.py` — `app_commands.Group` definitions (when needed)
- `commands.py` — root-group / top-level command mixin
- `<child>.py` — one file per child subgroup (e.g. `mod/link.py`)
- `helpers.py` — optional helper mixin; **subclassed by** command/listener mixins (do not re-list in `__init__.py`)
- `components.py` / `listeners.py` — UI / events when needed

Hard rules:

- Absolute imports only: `from src.cogs.mod.groups import ModGroups`
- Import groups from `.groups`, never from `__init__.py` (avoids cycles)
- `from discord.ext.commands import Cog` (not `commands.Cog`) so `commands.py` does not shadow `commands`
- Under `TYPE_CHECKING`, declare `client: DiscordBot` on mixins
- Use `@bot_decorators.defer`, `requires_location`, `requires_roles`, `handle_command_errors` from `src.utils.decorators`
- Prefer async Discord.py APIs; type-annotate public methods

Minimal command shape:

```python
class EngCommands(EngHelpers):
    client: DiscordBot

    @EngGroups.eng.command(name="ping", description="Get the bot's latency")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def eng_ping(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send(content=f"Pong!!!\nPing = `{round(self.client.latency * 1000)}ms`")
```

When adding a new cog package, ensure `scripts/check_cog_imports.py` still passes.

## Git / PR workflow

- Branch: `(discord-username)/feature-description`
- Commits: Conventional Commits — `type: short description` (`feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`)
- Open PRs against **`dev`**, never `main`
- Follow `.github/PULL_REQUEST_TEMPLATE.md`
- Do not commit unless the user asks

## Boundaries

### Always

- Match existing cog mixin patterns and absolute-import style
- Run Ruff + cog import check before considering code complete
- Keep secrets out of the tree (`src/.env` is local-only; use `src/.env.example` as the template)

### Ask first

- New dependencies in `pyproject.toml`
- Changes to CI/CD, deploy scripts, or guild/role/channel IDs in `src/utils/config.py`
- Schema / collection changes affecting MongoDB data

### Never

- Commit `BOT_TOKEN`, `MONGO_URI`, or other credentials
- Use relative imports inside `src/`
- Bypass hooks with `--no-verify`
- Force-push to `main` / `dev`
- Invent APIs or Discord.py patterns not already used nearby — mirror neighboring cogs

## Definition of done

1. Change fits the cog/utils layout above
2. `uv run ruff check .` and `uv run ruff format . --check` pass
3. `uv run scripts/check_cog_imports.py` passes if cogs/imports changed
4. No secrets or unrelated files staged
