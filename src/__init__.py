"""PESU community Discord bot package.

Package-level bootstrap lives here: environment loading and logging are configured
once on import, before the bot or any cog is constructed.
"""

import logging
from pathlib import Path

from dotenv import load_dotenv

__version__ = "0.1.0"

# Load environment variables before anything reads them (e.g. Config.resolve_env()).
# Explicit path so it works regardless of cwd (we now run as `python -m src` from the repo root).
load_dotenv(Path(__file__).resolve().parent / ".env")


class LoggingFormatter(logging.Formatter):
    """Colored console formatter."""

    black = "\x1b[30m"
    red = "\x1b[31m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    blue = "\x1b[34m"
    gray = "\x1b[38m"
    reset = "\x1b[0m"
    bold = "\x1b[1m"

    COLORS = {
        logging.DEBUG: gray + bold,
        logging.INFO: blue + bold,
        logging.WARNING: yellow + bold,
        logging.ERROR: red,
        logging.CRITICAL: red + bold,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelno, self.reset)
        fmt = "(black){asctime}(reset) (levelcolor){levelname:<8}(reset) (green){name}(reset) {message}"
        fmt = fmt.replace("(black)", self.black + self.bold)
        fmt = fmt.replace("(reset)", self.reset)
        fmt = fmt.replace("(levelcolor)", log_color)
        fmt = fmt.replace("(green)", self.green + self.bold)
        formatter = logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S", style="{")
        return formatter.format(record)


def _configure_logging() -> logging.Logger:
    """Configure the application logger (own handlers, no propagation to discord's)."""
    logger = logging.getLogger("discord.app")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(LoggingFormatter())

        log_file = Path(__file__).resolve().parent / "discord.log"
        file_handler = logging.FileHandler(filename=log_file, encoding="utf-8", mode="w")
        file_handler.setFormatter(
            logging.Formatter("[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{")
        )

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    return logger


logger = _configure_logging()

from src.bot import DiscordBot  # noqa: E402  (re-exported after bootstrap)

__all__ = ["DiscordBot", "LoggingFormatter", "__version__", "logger"]
