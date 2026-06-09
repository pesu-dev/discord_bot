#!/usr/bin/env bash
set -euo pipefail

readonly RUNNER="/usr/local/bin/deploy_runner.sh"
readonly TAG_REGEX='^([0-9a-f]{40}|dev|prod)$'

if [[ -z "${SSH_ORIGINAL_COMMAND:-}" ]]; then
  echo "No command provided."
  exit 1
fi

read -r -a ARGS <<<"${SSH_ORIGINAL_COMMAND}"
if [[ "${#ARGS[@]}" -ne 2 ]]; then
  echo "Expected command format: <dev|prod> <commit_sha|dev|prod>"
  exit 1
fi

TARGET_ENV="${ARGS[0]}"
IMAGE_TAG="${ARGS[1]}"

if [[ "${TARGET_ENV}" != "dev" && "${TARGET_ENV}" != "prod" ]]; then
  echo "Invalid environment '${TARGET_ENV}'. Allowed: dev, prod."
  exit 1
fi

if ! [[ "${IMAGE_TAG}" =~ ${TAG_REGEX} ]]; then
  echo "Invalid tag '${IMAGE_TAG}'. Expected 40-char commit sha, dev, or prod."
  exit 1
fi

if [[ "${TARGET_ENV}" == "dev" && "${IMAGE_TAG}" == "prod" ]]; then
  echo "Cannot deploy prod tag to dev environment."
  exit 1
fi

if [[ "${TARGET_ENV}" == "prod" && "${IMAGE_TAG}" == "dev" ]]; then
  echo "Cannot deploy dev tag to prod environment."
  exit 1
fi

exec sudo "${RUNNER}" "${TARGET_ENV}" "${IMAGE_TAG}"
