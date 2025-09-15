# PESU Discord Bot

[![License](https://img.shields.io/github/license/pesu-dev/discord_bot)](https://github.com/pesu-dev/discord_bot/blob/main/LICENSE)
[![Contributors](https://img.shields.io/github/contributors/pesu-dev/discord_bot)](https://github.com/pesu-dev/discord_bot/graphs/contributors)
[![Issues](https://img.shields.io/github/issues/pesu-dev/discord_bot)](https://github.com/pesu-dev/discord_bot/issues)
[![Project Board](https://img.shields.io/badge/project-board-blue)](https://github.com/orgs/pesu-dev/projects/4/views/8)

A powerful community management bot designed specifically for the PESU Discord Server. This bot provides essential moderation tools, anonymous messaging capabilities, user linking systems, and various utility commands to enhance the Discord experience for PESU students.

The bot is built with security and privacy in mind, ensuring safe and effective community management while maintaining user confidentiality.

> [!WARNING]
> The bot is hosted on a free tier AWS server with limited hardware. Users may experience lag during peak usage times.

## 🚀 Quick Start

### For Users

The bot is currently deployed and active in the PESU Discord Server. Use slash commands to interact with the bot:

- Type `/` in any channel to see available commands
- Use `/help` for detailed command documentation
- Contact moderators for support with bot-related issues

### For Developers

1. Check our [project board](https://github.com/orgs/pesu-dev/projects/4/views/8) for current work
2. Read the [contribution guidelines](.github/CONTRIBUTING.md)
3. Set up your development environment
4. Create a branch: `(discord-username)/feature-description`
5. Submit a PR to the `dev` branch

For detailed development setup and contribution instructions, see our [Contributing Guide](.github/CONTRIBUTING.md).

## 🏗️ Bot Architecture

### Project Structure

```
├── application.py          # Main application entry point (loads cogs, sets presence)
├── bot.py                  # Discord bot subclass with MongoDB attributes
├── faq.json                # FAQ responses data
├── requirements.txt        # Python dependencies (for non-uv users)
├── pyproject.toml          # Project metadata and tooling config
├── uv.lock                 # uv lockfile
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Local compose for services
├── LICENSE                 # Project license
├── README.md               # This file
├── cogs/                   # Bot functionality modules (Discord.py cogs)
│   ├── events/             # Event handlers
│   │   └── general.py      # General event handling (member joins, etc.)
│   └── interactions/       # Command interactions
│       └── slash/          # Slash commands implementation
│           ├── anon.py     # Anonymous messaging system
│           ├── help.py     # Help and command documentation
│           ├── link.py     # User linking and verification
│           ├── mod.py      # Moderation commands
│           └── utils.py    # Utility commands (ping, uptime, etc.)
└── utils/                  # Shared utilities and configuration helpers
    ├── config.py           # Guild/role/channel IDs and access helpers
    └── general.py          # General helper functions
```

### Cogs System

The bot uses Discord.py's cogs system to organize functionality into modular components:

- **Events Cogs**: Handle Discord events such as member joins, message events, and server updates
- **Slash Command Cogs**: Implement modern Discord slash commands for user interactions
- **Utility Functions**: Shared helper functions used across different cogs

### Database Collections

The bot maintains several MongoDB collections:
- `link`: Stores Discord-PESU account links
- `student`: Student linking data
- `anonban`: Anonymous messaging ban records
- `mute`: Server mute records

##  Configuration

The bot's behavior is controlled primarily through environment variables and code-based configuration:

Refer to our Contributing Guide for environment setup and the list of variables: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md). An example file is provided at [`.env.example`](.env.example).

### `utils/config.py`
Holds guild-specific role and channel ID mappings and exposes helpers like `get_role`/`get_channel`.

### `faq.json`
Stores frequently asked questions and their responses for quick access.

## 🤝 Contributing to PESU Discord Bot

Made with ❤️ by

[![Contributors](https://contrib.rocks/image?repo=pesu-dev/discord_bot&nocache=1)](https://github.com/pesu-dev/discord_bot/graphs/contributors)

*Powered by [contrib.rocks](https://contrib.rocks)*

We welcome contributions from the PESU community! Whether you're fixing bugs, adding new features, or improving documentation, your help is appreciated.

**👉 [Read our detailed Contributing Guide](.github/CONTRIBUTING.md)** for complete setup instructions and development workflow.

## 🔐 Security and Privacy

- **No Credential Storage**: The bot does not store Discord or PESU passwords
- **Secure Database**: All data is stored securely in MongoDB with proper access controls
- **Role-based Access**: Commands are restricted based on user permissions and server roles

## 📊 Project Status

- **Active Development**: The bot is actively maintained and updated
- **Community Driven**: Features are developed based on community needs
- **Production Ready**: Currently deployed and serving the PESU Discord community

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

For questions, support, or feature requests, please visit our [project board](https://github.com/orgs/pesu-dev/projects/4/views/8) or join the discussion on the PESU Discord server.





