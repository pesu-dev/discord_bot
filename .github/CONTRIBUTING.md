# Contributing to PESU Discord Bot

Thank you for your interest in contributing to the PESU Discord Bot! This document provides guidelines and instructions for setting up your development environment and contributing to the project.

---

<!-- markdownlint-disable MD033 -->
<details>
<summary>Table of Contents</summary>

- [Contributing to PESU Discord Bot](#contributing-to-pesu-discord-bot)
- [Getting Started](#getting-started)
- [Development Environment Setup](#-development-environment-setup)
  - [Prerequisites](#prerequisites)
  - [Setting Up Your Environment](#setting-up-your-environment)
  - [Set Up Environment Variables](#set-up-environment-variables)
  - [Database Setup](#database-setup)
- [Running the Bot](#-running-the-bot)
- [Submitting Changes](#-submitting-changes)
  - [Create a Branch](#-create-a-branch)
  - [Make and Commit Changes](#-make-and-commit-changes)
  - [Push and Open a Pull Request](#-push-and-open-a-pull-request)
- [Need Help?](#-need-help)
- [Security](#-security)
- [Code Style Guide](#-code-style-guide)
  - [General Guidelines](#-general-guidelines)
- [GitHub Labels](#-github-labels)
- [Feature Suggestions](#-feature-suggestions)
- [License](#-license)

</details>

---

## Getting Started

### Development Workflow

The standard workflow for contributing is as follows:

1. Clone the repository to your local machine, or fork it and then clone your fork.
2. Create a new branch with the format `(discord-username)/feature-description` for your feature or bug fix.
3. Make your changes and commit them with clear, descriptive messages.
4. Push your branch to the repository (or your fork).
5. Create a Pull Request (PR) against the repository's `dev` branch (not `main`).
6. Follow the PR template when creating your pull request.
7. Wait for review and feedback from the maintainers, address any comments or suggestions.
8. Once approved, your changes will be merged into the `dev` branch.

**⚠️ Important**: Direct PRs to `main` will be closed. All contributions must target the `dev` branch.

---

## 🛠 Development Environment Setup

This section provides instructions for setting up your development environment to work on the PESU Discord Bot project.

### Prerequisites

- Linux environment (native Linux or Windows via WSL)
- Python 3.9 or higher
- Git
- MongoDB (local instance or cloud service like MongoDB Atlas)
- Discord Application with Bot Token

> [!NOTE]
> Development is supported on Linux only. On Windows, use WSL.

### Setting Up Your Environment

#### Using uv (recommended)

1. **Install uv:**

   ```bash
   curl -fsSL https://astral.sh/uv/install.sh | sh
   ```

2. **Clone the repository (or your fork) and navigate to the project:**

   ```bash
   # Option 1: Clone the main repository
   git clone https://github.com/pesu-dev/discord_bot.git
   cd discord_bot

   # Option 2: Clone your fork
   git clone https://github.com/your-github-username/discord_bot.git
   cd discord_bot
   ```

3. **Install Git hooks (required):**

   ```bash
   .githooks/install.sh
   ```

   This installs symlinked hooks that run automated checks (Ruff linting, branch name warnings, and commit message validation) on commit/push.

4. **Install project dependencies from `pyproject.toml`:**

   ```bash
   uv sync
   ```

### Set Up Environment Variables

1. **Create a `.env` file in the `src/` directory:**

   ```bash
   touch src/.env
   ```

2. **Configure your environment variables:**
   Open the `src/.env` file and add the following variables (see `src/.env.example` for a template):

   ```env
   MONGO_URI=""
   DB_NAME=""
   ASKPESU_API=""
   BOT_TOKEN=""
   APP_ENV=""
   BOT_PREFIX=""
   ```

   Replace the placeholder values with your actual credentials:
   - `MONGO_URI`: MongoDB connection string
   - `DB_NAME`: Database name for the bot
   - `ASKPESU_API`: Base URL for AskPESU API
   - `BOT_TOKEN`: Discord bot token
   - `APP_ENV`: Environment name (`dev` or `prod`)
   - `BOT_PREFIX`: Command prefix for legacy/message commands

### Database Setup

The bot uses MongoDB to store various data including:

- User linking records
- Anonymous message ban records
- Moderation logs
- Mute records

Ensure you have:

1. A MongoDB instance running (local or cloud)
2. Proper connection string in your `.env` file
3. Appropriate database permissions for read/write operations

---

## 🧰 Running the Bot

To run the bot locally for development:

1. **Run the bot** (from the `src` directory):

   ```bash
   cd src
   uv run application.py
   ```

The bot will start and connect to Discord. You should see connection logs in your terminal indicating successful startup.

**Note**: Make sure you have set up a test Discord server or have appropriate permissions in the PESU Discord server for development testing.

---

## 🚀 Submitting Changes

### 🔀 Create a Branch

Start by creating a new branch following the naming convention:

```bash
git checkout -b your-discord-username/feature-description
```

Replace `your-discord-username` with your actual Discord username and `feature-description` with a brief description of what you're working on.

### ✏ Make and Commit Changes

After making your changes, commit them with clear messages:

```bash
git add required-files-only
git commit -m "Add new moderation command for timeout management"
```

Use descriptive commit messages that explain what the change does.

#### Commit message convention

We follow a lightweight Conventional Commits style for commit subjects. The hooks will warn if the format is not followed.

- Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`
- Format: `type: short description`
- Constraints: minimum 10 characters total; description up to 50 characters

Examples:

```text
feat: add user authentication
fix: handle None guild_id in moderation log
docs: update setup instructions to use uv
```

### 📤 Push and Open a Pull Request

1. **Push your branch to the repository (or your fork):**

   ```bash
   git push origin your-discord-username/feature-description
   ```

2. **Open a Pull Request on GitHub targeting the `dev` branch.**

3. **Follow the PR template when creating your pull request.**

---

## ❓ Need Help?

If you get stuck or have questions:

1. Check the [README.md](../README.md) for setup and usage info.
2. Review the [project board](https://github.com/orgs/pesu-dev/projects/4/views/8) to see current work and track progress.
3. Reach out to the maintainers on PESU Discord.
   - Use the appropriate development channels for questions.
   - Search for existing discussions before posting.
4. Open a new issue if you're facing something new or need clarification.

---

## 🔐 Security

If you discover a security vulnerability, **please do not open a public issue**.

Instead, report it privately by contacting the maintainers. We take all security concerns seriously and will respond promptly.

**Important**: Never commit sensitive information like bot tokens, database credentials, or API keys to the repository.

---

## ✨ Code Style Guide

To keep the codebase clean and maintainable, please follow these conventions:

### ✅ General Guidelines

- Write clean, readable code with meaningful variable and function names
- Use type hints where appropriate (Python 3.9+ syntax)
- Keep functions focused and modular
- Follow PEP 8 style guidelines
- Use async/await for all Discord.py operations

---

## 🏷 GitHub Labels

We use GitHub labels to categorize issues and PRs. Here's a quick guide to what they mean:

| Label              | Purpose                                         |
| ------------------ | ----------------------------------------------- |
| `good first issue` | Beginner-friendly, simple issues to get started |
| `bug`              | Something is broken or not working as intended  |
| `enhancement`      | Proposed improvements or new features           |
| `documentation`    | Docs, comments, or README-related updates       |
| `question`         | Open questions or clarifications                |
| `help wanted`      | Maintainers are seeking help or collaboration   |

When creating or working on an issue/PR, feel free to suggest an appropriate label if not already applied.

---

## 🧩 Feature Suggestions

If you want to propose a new feature:

1. Check if it already exists on the [project board](https://github.com/orgs/pesu-dev/projects/4/views/8)
2. Open a new issue with a clear description
3. Explain the use case and how it benefits the PESU Discord community
4. Consider Discord's rate limits and bot permissions

---

## 📄 License

By contributing to this repository, you agree that your contributions will be licensed under the same license as the project. See [`LICENSE`](../LICENSE) for full license text.
