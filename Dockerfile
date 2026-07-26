FROM python:3.13.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    TZ=Asia/Shanghai

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY docker ./docker

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && chown -R app:app /app

RUN chmod +x docker/entrypoint.sh

EXPOSE 8008

USER app

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "--chdir", "/app/src", "config.wsgi:application", "--bind", "0.0.0.0:8008", "--workers", "3", "--timeout", "120"]
