from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.health import clear_health, is_heartbeat_fresh, touch_health

_HEALTH_SCRIPT = Path(__file__).resolve().parents[3] / "src" / "utils" / "health.py"
_DISCORD_LOG = Path(__file__).resolve().parents[3] / "src" / "discord.log"


def _set_heartbeat(monkeypatch: pytest.MonkeyPatch, path: Path, max_age: str = "60") -> None:
    monkeypatch.setenv("HEALTHCHECK_PATH", str(path))
    monkeypatch.setenv("HEALTHCHECK_MAX_AGE", max_age)


def test_heartbeat_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_heartbeat(monkeypatch, tmp_path / "healthy")
    assert is_heartbeat_fresh() is False


def test_heartbeat_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "healthy"
    _set_heartbeat(monkeypatch, path)
    touch_health()
    assert path.is_file()
    assert is_heartbeat_fresh() is True


def test_heartbeat_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "healthy"
    _set_heartbeat(monkeypatch, path, max_age="10")
    touch_health()
    old = time.time() - 30
    os.utime(path, (old, old))
    assert is_heartbeat_fresh() is False


def test_clear_health_missing_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "healthy"
    _set_heartbeat(monkeypatch, path)
    clear_health()
    touch_health()
    assert path.is_file()
    clear_health()
    assert not path.exists()


def test_health_probe_script_exit_codes(tmp_path: Path) -> None:
    path = tmp_path / "healthy"
    env = {**os.environ, "HEALTHCHECK_PATH": str(path), "HEALTHCHECK_MAX_AGE": "60"}
    missing = subprocess.run([sys.executable, str(_HEALTH_SCRIPT)], env=env, check=False)
    assert missing.returncode == 1
    path.touch()
    fresh = subprocess.run([sys.executable, str(_HEALTH_SCRIPT)], env=env, check=False)
    assert fresh.returncode == 0


def test_health_probe_does_not_import_src_package(tmp_path: Path) -> None:
    _DISCORD_LOG.write_text("sentinel", encoding="utf-8")
    env = {**os.environ, "HEALTHCHECK_PATH": str(tmp_path / "missing")}
    subprocess.run([sys.executable, str(_HEALTH_SCRIPT)], env=env, check=False)
    assert _DISCORD_LOG.read_text(encoding="utf-8") == "sentinel"


async def test_health_task_touches_when_ready_and_mongo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    path = tmp_path / "healthy"
    _set_heartbeat(monkeypatch, path)
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.is_ready = MagicMock(return_value=True)
    bot.is_closed = MagicMock(return_value=False)
    bot.mongo = MagicMock()
    await DiscordBot.health_task.coro(bot)
    assert path.is_file()


@pytest.mark.parametrize(
    ("ready", "closed", "has_mongo"),
    [
        (False, False, True),
        (True, True, True),
        (True, False, False),
    ],
)
async def test_health_task_skips_when_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ready: bool,
    closed: bool,
    has_mongo: bool,
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    path = tmp_path / "healthy"
    _set_heartbeat(monkeypatch, path)
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.is_ready = MagicMock(return_value=ready)
    bot.is_closed = MagicMock(return_value=closed)
    bot.mongo = MagicMock() if has_mongo else None
    await DiscordBot.health_task.coro(bot)
    assert not path.exists()


async def test_before_health_task_waits_until_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.wait_until_ready = AsyncMock()
    await DiscordBot.before_health_task(bot)
    bot.wait_until_ready.assert_awaited()


async def test_bot_close_clears_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    path = tmp_path / "healthy"
    _set_heartbeat(monkeypatch, path)
    path.touch()
    from src.bot import DiscordBot

    bot = DiscordBot()
    bot.logger = MagicMock()
    logs = MagicMock()
    logs.send = AsyncMock()
    bot.config = MagicMock()
    bot.config.bot_logs_channel = logs
    bot.status_task.is_running = MagicMock(return_value=False)
    bot.sync_archives_loop.is_running = MagicMock(return_value=False)
    bot.health_task.is_running = MagicMock(return_value=True)
    bot.health_task.cancel = MagicMock()

    with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
        await bot.close()

    bot.health_task.cancel.assert_called_once()
    assert not path.exists()
