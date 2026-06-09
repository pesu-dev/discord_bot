#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "deploy_runner.sh must run as root."
  exit 1
fi

if [[ "${#}" -ne 2 ]]; then
  echo "Usage: deploy_runner.sh <dev|prod> <tag>"
  exit 1
fi

TARGET_ENV="${1}"
IMAGE_TAG="${2}"

if [[ "${TARGET_ENV}" != "dev" && "${TARGET_ENV}" != "prod" ]]; then
  echo "Invalid environment '${TARGET_ENV}'."
  exit 1
fi

APP_DIR="/srv/discord_bot"
CONFIG_FILE="/etc/discord_bot/deploy.env"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
PROJECT_NAME="discord_bot_${TARGET_ENV}"
CONTAINER_NAME="discord_bot_${TARGET_ENV}"
HEALTH_TIMEOUT_SECONDS=180
POLL_INTERVAL_SECONDS=5

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${CONFIG_FILE}"
fi

REPO_OWNER="${REPO_OWNER:-pesu-dev}"
DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME:-discord_bot}"

# The dev bot only needs to run when dev differs from prod. A prod deploy
# promotes the current dev build to prod, so once prod is healthy the dev
# environment is redundant and gets taken down.
take_down_dev() {
  if ! docker container inspect "discord_bot_dev" >/dev/null 2>&1; then
    echo "Dev environment is not running; nothing to take down."
    return 0
  fi
  echo "Taking down dev environment (now superseded by prod)."
  ENV_FILE=".env.dev" TARGET_ENV="dev" \
    docker compose -p "discord_bot_dev" -f "${COMPOSE_FILE}" down --remove-orphans ||
    echo "Warning: failed to fully take down dev environment."
}

if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory ${APP_DIR} does not exist."
  exit 1
fi

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file ${COMPOSE_FILE} does not exist."
  exit 1
fi

if [[ ! -f "${APP_DIR}/.env.${TARGET_ENV}" ]]; then
  echo "Missing required env file ${APP_DIR}/.env.${TARGET_ENV}."
  exit 1
fi

export IMAGE_TAG
export REPO_OWNER
export DOCKER_IMAGE_NAME
export TARGET_ENV
export ENV_FILE=".env.${TARGET_ENV}"

echo "Deploying ${DOCKER_IMAGE_NAME}:${IMAGE_TAG} to ${TARGET_ENV}"
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" pull
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" up -d --remove-orphans

deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
  state_status="$(docker inspect --format '{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null || true)"

  if [[ "${health_status}" == "healthy" ]]; then
    echo "Container ${CONTAINER_NAME} is healthy."
    if [[ "${TARGET_ENV}" == "prod" ]]; then
      take_down_dev
    fi
    docker image prune -f --filter "until=168h" >/dev/null 2>&1 || true
    exit 0
  fi

  if [[ "${health_status}" == "no-healthcheck" ]]; then
    echo "Container ${CONTAINER_NAME} has no HEALTHCHECK configured."
    exit 1
  fi

  if [[ "${health_status}" == "unhealthy" || "${state_status}" == "exited" || "${state_status}" == "dead" ]]; then
    echo "Container ${CONTAINER_NAME} failed health checks (state=${state_status}, health=${health_status})."
    docker logs "${CONTAINER_NAME}" --tail 100 || true
    exit 1
  fi

  sleep "${POLL_INTERVAL_SECONDS}"
done

echo "Timed out waiting for ${CONTAINER_NAME} to become healthy."
docker logs "${CONTAINER_NAME}" --tail 100 || true
exit 1
