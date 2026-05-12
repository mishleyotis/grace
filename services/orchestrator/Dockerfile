FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock* ./
COPY libs/shared/ libs/shared/
COPY services/orchestrator/ services/orchestrator/

RUN uv sync --frozen --no-dev --package grace-orchestrator || \
    uv sync --no-dev --package grace-orchestrator

EXPOSE 8080
CMD ["uv", "run", "--package", "grace-orchestrator", "python", "-m", "grace_orchestrator.server"]
