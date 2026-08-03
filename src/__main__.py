import os

from src import DiscordBot


def main() -> None:
    bot = DiscordBot()
    token = os.getenv("BOT_TOKEN")
    if not token:
        bot.logger.error("BOT_TOKEN environment variable not set")
        return
    bot.run(token)


if __name__ == "__main__":
    main()
