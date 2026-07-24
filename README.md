# PESU Discord Bot

[![License](https://img.shields.io/github/license/pesu-dev/discord_bot)](https://github.com/pesu-dev/discord_bot/blob/main/LICENSE)
[![Contributors](https://img.shields.io/github/contributors/pesu-dev/discord_bot)](https://github.com/pesu-dev/discord_bot/graphs/contributors)
[![Issues](https://img.shields.io/github/issues/pesu-dev/discord_bot)](https://github.com/pesu-dev/discord_bot/issues)
[![Project Board](https://img.shields.io/badge/project-board-blue)](https://github.com/orgs/pesu-dev/projects/4/views/8)
![RepoVital](https://api.repovital.com/badge/pesu-dev/discord_bot)

A powerful community management bot designed specifically for the PESU Discord Server. This bot provides essential moderation tools, anonymous messaging capabilities, user linking systems, and various utility commands to enhance the Discord experience for PESU students.

The bot is built with security and privacy in mind, ensuring safe and effective community management while maintaining user confidentiality.

> [!WARNING]
> The bot is hosted on a free-tier GCP `e2-micro` VM with limited hardware. Users may experience lag during peak usage times.

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

```text
├── pyproject.toml              # Project metadata and dependencies
├── uv.lock                     # uv lockfile
├── Dockerfile                  # Container image definition
├── LICENSE                     # Project license
├── README.md                   # This file
├── scripts/                    # Operational scripts
│   ├── check_cog_imports.py    # CI check: import every cog package (catches import cycles)
│   └── sync_guild_commands.py  # Deploy-time guild command sync
└── src/                        # Discord bot package (run via `python -m src`)
    ├── __init__.py             # Package bootstrap: env loading, logging, version
    ├── __main__.py             # Entry point for `python -m src`
    ├── bot.py                  # DiscordBot subclass (setup_hook, cog loading, events)
    ├── .env.example            # Example environment variables
    ├── data/                   # Static data files
    │   └── faq.json            # FAQ responses data
    ├── cogs/                   # Bot functionality, one package per cog (Discord.py cogs)
    │   ├── anon/               # Anonymous messaging (send)
    │   ├── eng/                # Bot engineering commands (ping, uptime, reload)
    │   ├── events/             # Event listeners (member joins, ghost pings, etc.)
    │   ├── general/            # General user commands (info, count, faq, roles, ...)
    │   ├── help/               # Help menu
    │   └── mod/                # Moderation + account-link & anon moderation
    └── utils/                  # Shared utilities and configuration helpers
        ├── config.py           # Environment, guild/role/channel IDs and access helpers
        ├── decorators.py       # Command decorators (defer, permission/location checks, errors)
        └── general.py          # Shared helpers + cog discovery/reload helpers
```

### Cogs System

The bot uses Discord.py's cogs system to organize functionality into modular components. **Each cog is a package** under `src/cogs/<name>/`, and every package with an `__init__.py` is auto-discovered and loaded as an extension. Files within a cog package follow a uniform scheme:

- **`__init__.py`**: The `commands.Cog` subclass (composed from groups + commands/listeners mixins), lifecycle bits (task loops, `on_ready`), and the `setup()` entrypoint.
- **`commands.py`**: Command definitions for the cog's root group (or top-level commands), as a `*Commands` mixin. When the cog has helpers, this class **subclasses** `*Helpers` so helper methods type-check on `self`.
- **`groups.py`**: The `app_commands.Group` definitions (only when the cog uses groups).
- **child-group file** (e.g. `mod/link.py`): each child subgroup gets its own file; root commands stay in `commands.py`. Child-group command mixins that need helpers also subclass `*Helpers`.
- **`helpers.py`**: Internal helper methods / shared logic (optional). Inherited by `*Commands` / `*Listeners`, not listed again in `__init__.py`.
- **`components.py`**: Discord UI such as views, selects, and buttons (optional).
- **`listeners.py`**: Event listeners (used by the `events` cog, which has no slash commands). Subclasses `*Helpers` when helpers exist.

Shared, cross-cog utilities live in `src/utils/` rather than inside any single cog.

### Database Collections

The bot maintains several MongoDB collections. Document shapes and typed CRUD live together in `src/data/mongo/`; access them via `client.stores` (`links`, `students`, `anonbans`, `mutes`):

- `link`: Stores Discord-PESU account links (`Link` / `LinkStore`)
- `student`: Student linking data (`Student` / `StudentStore`)
- `anonban`: Anonymous messaging ban records (`AnonBan` / `AnonBanStore`)
- `mute`: Server mute records (`Mute` / `MuteStore`)

## Configuration

The bot's behavior is controlled primarily through environment variables and code-based configuration:

Refer to our Contributing Guide for environment setup and the list of variables: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md). An example file is provided at [`src/.env.example`](src/.env.example).

### `src/utils/config.py`

Holds guild-specific role and channel ID mappings and exposes helpers like `get_role`/`get_channel`.

### `faq.json`

Stores frequently asked questions and their responses for quick access.

## 🤝 Contributing to PESU Discord Bot

Made with ❤️ by

[![Contributors](https://contrib.rocks/image?repo=pesu-dev/discord_bot&nocache=1)](https://github.com/pesu-dev/discord_bot/graphs/contributors)

*Powered by [contrib.rocks](https://contrib.rocks)*

We welcome contributions from the PESU community! Whether you're fixing bugs, adding new features, or improving documentation, your help is appreciated.

**👉 [Read our detailed Contributing Guide](.github/CONTRIBUTING.md)** for complete setup instructions and development workflow.

## 🚢 CI/CD and Deployment

The project uses an immutable-image promotion flow designed for free-tier hosting:

- PR to `dev`: lint + source checks + Docker image build validation (no push)
- Merge to `dev`: checks run again, image is pushed to GHCR as `<commit_sha>`, then deployed to dev
- Post-dev health success: deployed SHA is retagged as `dev`
- Manual prod promotion: `dev -> main` fast-forward, deploy the same immutable SHA, and retag as `prod` only on success
- Prod failure path: automatic rollback deploy to the previous `prod` tag

Key deployment files:

- [`.github/workflows/dev_deploy.yml`](.github/workflows/dev_deploy.yml)
- [`.github/workflows/prod_deploy.yml`](.github/workflows/prod_deploy.yml)
- [`.github/workflows/build_and_push_image.yml`](.github/workflows/build_and_push_image.yml)
- [`.github/workflows/ghcr_cleanup.yml`](.github/workflows/ghcr_cleanup.yml)
- [`ops/deploy/README.md`](ops/deploy/README.md)

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
