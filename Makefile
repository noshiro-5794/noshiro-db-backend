UV ?= uv
RUN ?= $(UV) run
MANAGE ?= $(RUN) python src/manage.py
HOST ?= 0.0.0.0
PORT ?= 8008

.PHONY: sync lock upgrade format lint test check migrations migrate run worker beat shell incremental-status

sync:
	$(UV) sync --frozen

lock:
	$(UV) lock

upgrade:
	$(UV) lock --upgrade
	$(UV) sync

format:
	$(RUN) ruff format src tests

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check src tests

test:
	$(RUN) pytest

check: lint test
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run

migrations:
	$(MANAGE) makemigrations

migrate:
	$(MANAGE) migrate

run:
	$(MANAGE) runserver $(HOST):$(PORT)

worker:
	$(RUN) celery --workdir src -A config.celery:app worker -l info

beat:
	$(RUN) celery --workdir src -A config.celery:app beat -l info

shell:
	$(MANAGE) shell

incremental-status:
	$(MANAGE) incremental_sync --status
