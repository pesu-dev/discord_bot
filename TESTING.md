# Testing

How we test the PESU Discord bot.

## Pyramid

| Layer                       | What                                                                       | How                                    |
| --------------------------- | -------------------------------------------------------------------------- | -------------------------------------- |
| **Unit** (majority)         | Pure helpers, decorators, command callbacks with mocked Discord/Mongo/HTTP | `pytest -m unit`                       |
| **Integration** (selective) | Real MongoDB via Testcontainers for mute / anonban / join-role flows       | `pytest -m integration` (needs Docker) |
| **Smoke**                   | Cog import check (existing CI script)                                      | `uv run scripts/check_cog_imports.py`  |

We do **not** run live Discord e2e in CI (tokens, flakiness, rate limits).

Discord interactions are mocked (`unittest.mock` / fixtures in `tests/conftest.py`). SimCord is deferred for a later evaluation.

## Commands

```bash
uv sync --extra dev

# Fast local loop (also what pre-commit should prefer)
uv run pytest -m unit --cov=src --cov-report=term-missing

# Needs Docker (Testcontainers). Ryuk is disabled for Colima portability.
uv run pytest -m integration

# Everything
uv run pytest
```

Coverage floor is **60%** on `src/` (see `[tool.coverage.report]` in `pyproject.toml`), enforced on the unit CI job.

## Layout

```text
tests/
  conftest.py           # shared fixtures (Interaction, Member, Config, bot)
  helpers.py            # get_callback() for app_commands Command objects
  fixtures/             # optional static JSON fixtures
  unit/                 # mirrors src/
  integration/          # Testcontainers Mongo
```

## Conventions

- Prefer asserting **outcomes** (DB docs, followup content, roles changed), not mock call sequences that mirror implementation.
- Invoke slash handlers via `tests.helpers.get_callback(cmd.some_command)` — Discord wraps methods in `Command` objects.
- Cancel / avoid starting cog background tasks when constructing real cog classes in tests (patch `__init__` or cancel loops in teardown).
- Use absolute imports (`from src...`) the same as production code.
- Never require `BOT_TOKEN` or a real `src/.env` for automated tests (`APP_ENV=local` is set in `conftest.py`).

## When to add which test

- New pure helper / parser / policy → **unit**
- New decorator behavior → **unit** with fake Interaction
- New Mongo write path that must survive real queries → **integration** (plus a unit with AsyncMock)
- New HTTP client usage → **unit** with `respx`
