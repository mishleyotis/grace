FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock* ./
COPY libs/shared/ libs/shared/
COPY services/site-mirror/ services/site-mirror/

RUN uv sync --frozen --no-dev --package grace-site-mirror || \
    uv sync --no-dev --package grace-site-mirror

EXPOSE 8080
CMD ["uv", "run", "--package", "grace-site-mirror", "python", "-m", "grace_site_mirror.server"]
