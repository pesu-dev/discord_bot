# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install the exact locked dependencies (no dev tooling, don't install the project itself).
# Cache mount keeps the uv download cache out of the image layers.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim-bookworm

WORKDIR /app

# Git commit SHA baked in at build time (used by deploy workflows to detect command changes).
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision=${GIT_SHA}

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=4 \
  CMD python src/utils/health.py

CMD ["python", "-m", "src"]
