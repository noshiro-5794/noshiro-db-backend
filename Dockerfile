ARG PYTHON_VERSION=3.13.14
ARG UV_VERSION=0.11.31
ARG PYTHON_BASE_IMAGE=python:${PYTHON_VERSION}-slim-bookworm

FROM ${PYTHON_BASE_IMAGE} AS runtime
ARG UV_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    TZ=Asia/Shanghai

WORKDIR /app

LABEL org.opencontainers.image.title="noshiro-db-backend" \
      org.opencontainers.image.description="Noshiro DB API runtime" \
      org.opencontainers.image.source="https://github.com/noshiro-5794/noshiro-db-backend"

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && python -m pip install --no-cache-dir "uv==${UV_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY docker ./docker

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && chown -R app:app /app

RUN chmod +x docker/entrypoint.sh docker/celery_healthcheck.sh docker/beat_healthcheck.sh

EXPOSE 8008

USER app

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--chdir", "/app/src", "config.wsgi:application", "--bind", "0.0.0.0:8008", "--workers", "3", "--timeout", "120"]
