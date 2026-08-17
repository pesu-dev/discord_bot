FROM python:3.13-slim-bookworm

# Pull in the uv binary from its official image
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Git commit SHA baked in at build time (used by deploy workflows to detect command changes).
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision=${GIT_SHA}

# Install the exact locked dependencies (no dev tooling, don't install the project itself)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy only the application source
COPY src/ ./src/

# Use the project's virtual environment by default
ENV PATH="/app/.venv/bin:$PATH"

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=4 \
  CMD python src/utils/health.py

# Run the bot as a package (python -m src) from /app
CMD ["python", "-m", "src"]
