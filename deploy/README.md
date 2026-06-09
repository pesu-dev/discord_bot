# Deployment

These are the host-side scripts used to deploy the bot onto the VM. They are
included for transparency; **no secrets live in this directory**. The real
runtime secrets (`.env.dev`, `.env.prod`) and the host config
(`/etc/discord_bot/deploy.env`) only exist on the server and are never committed.

## How a deploy happens

1. CI (`.github/workflows/dev_deploy.yml` / `prod_deploy.yml`) builds and pushes
   an immutable image to GHCR tagged with the commit SHA.
2. CI SSHes into the VM. The SSH key is locked to a **forced command** so the
   only thing it can run is `deploy_gate.sh`, receiving e.g. `dev <sha>` via
   `SSH_ORIGINAL_COMMAND`.
3. `deploy_gate.sh` strictly validates the arguments (environment must be
   `dev`/`prod`, tag must be a 40-char SHA or `dev`/`prod`) and then
   `sudo`-executes `deploy_runner.sh`.
4. `deploy_runner.sh` (root) pulls the image, runs `docker compose up`, and waits
   for the container's `HEALTHCHECK` to report healthy before succeeding.

## Dev vs prod lifecycle

The `dev` and `prod` environments run as separate Compose projects
(`discord_bot_dev` / `discord_bot_prod`) on the same host. The dev bot is only
meant to run while dev is ahead of prod:

- A **dev deploy** brings the dev environment up.
- A **prod deploy**, once the prod container is confirmed healthy, tears the dev
  environment down (`docker compose -p discord_bot_dev down`) — because promoting
  to prod means dev and prod now run the same build, so a separate dev bot is
  redundant.

The teardown only happens after prod is healthy, so a failed or rolled-back prod
deploy leaves the dev environment untouched.

## Files

| File                 | Purpose                                              | Lives on host at              |
| -------------------- | ---------------------------------------------------- | ----------------------------- |
| `deploy_gate.sh`     | SSH forced-command entrypoint; validates input       | invoked via `authorized_keys` |
| `deploy_runner.sh`   | Root deploy runner (pull + compose up + healthcheck) | `/usr/local/bin/`             |
| `docker-compose.yml` | Service definition consumed by the runner            | `/srv/discord_bot/`           |
| `deploy.env.example` | Template for non-secret host config                  | `/etc/discord_bot/deploy.env` |

## Host layout

- `/srv/discord_bot/docker-compose.yml` — compose file
- `/srv/discord_bot/.env.<env>` — runtime secrets per environment (`.env.dev`, `.env.prod`)
- `/etc/discord_bot/deploy.env` — non-secret config (`REPO_OWNER`, `DOCKER_IMAGE_NAME`)
- `/usr/local/bin/deploy_runner.sh` — the runner, executed as root

## Server setup (one-time)

1. Copy `deploy.env.example` to `/etc/discord_bot/deploy.env` and adjust values.
2. Place `docker-compose.yml` at `/srv/discord_bot/` and create the
   `/srv/discord_bot/.env.dev` (and `.env.prod`) secret files.
3. Install `deploy_runner.sh` to `/usr/local/bin/` (root-owned, mode `0755`).
4. Restrict the deploy user's sudoers to only run the runner as root, e.g.:

   ```sudoers
   deploy ALL=(root) NOPASSWD: /usr/local/bin/deploy_runner.sh
   ```

5. Pin the CI SSH key to the gate via `~/.ssh/authorized_keys`:

   ```text
   command="/usr/local/bin/deploy_gate.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... ci-deploy
   ```
