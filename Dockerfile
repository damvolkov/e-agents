# =============================================================================
# e-agents Dockerfile
# =============================================================================

# -----------------------------------------------------------------------------
# Builder Stage
# -----------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.8-python3.13-bookworm AS builder

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends git portaudio19-dev libc++1 && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

COPY uv.lock pyproject.toml README.md ./
COPY .git/ ./.git/

RUN git config --global --add safe.directory /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

RUN rm -rf .venv/lib/python*/site-packages/pip* \
           .venv/lib/python*/site-packages/setuptools* \
           .venv/include

# -----------------------------------------------------------------------------
# Runtime Stage
# -----------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.8-python3.13-bookworm

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends curl git libportaudio2 libc++1 && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

RUN groupadd -g 1000 appuser && \
    useradd -m -u 1000 -g appuser -d /app -s /bin/bash appuser && \
    chown -R appuser:appuser /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/.git /app/.git
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/pyproject.toml /app/pyproject.toml
COPY --from=builder --chown=appuser:appuser /app/uv.lock /app/uv.lock
COPY --from=builder --chown=appuser:appuser /app/README.md /app/README.md

USER 1000

RUN git config --global --add safe.directory /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "e_agents.main:create_api_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
