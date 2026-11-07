# SMARAN: common tasks. Run from the repo root.
COMPOSE ?= docker compose -f infra/docker-compose.yml --env-file infra/.env
PYTHON  ?= python3

.PHONY: help env check-env secrets config build up down logs ps seed seed-fake test lint install-dev

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

env: ## create infra/.env from the example (once)
	@test -f infra/.env || (cp infra/.env.example infra/.env && echo "Created infra/.env: now set the secrets (make secrets)")

secrets: ## print fresh secrets to paste into infra/.env
	@sh infra/scripts/gen_secrets.sh

check-env: env
	@sh infra/scripts/check_env.sh infra/.env

config: ## validate the compose file (uses the example env, no secrets needed)
	docker compose -f infra/docker-compose.yml --env-file infra/.env.example config -q
	@echo "compose config OK"

build: check-env ## build all images
	$(COMPOSE) build

up: check-env ## start the stack (detached)
	$(COMPOSE) up -d --build

down: ## stop the stack (keeps volumes)
	$(COMPOSE) down

logs: ## follow logs
	$(COMPOSE) logs -f --tail=100

ps: ## service status
	$(COMPOSE) ps

seed: ## run the API's seed.py (owned by Claude 1.1) inside the api container
	$(COMPOSE) exec api python seed.py

seed-fake: ## fill fake patients/sessions/alerts for demos (mocks/fake_data) and run the insights scan
	$(COMPOSE) run --rm --no-deps -e PYTHONPATH=/app -v "$(CURDIR)/mocks:/mocks:ro" api \
	  python /mocks/fake_data/fill_fake_data.py --run-pipeline

install-dev: ## install API + test tooling on the host
	$(PYTHON) -m pip install -r services/api/requirements.txt -r infra/requirements/dev.txt

test: ## run the API test-suite (SQLite by default; TEST_DATABASE_URL=... for Postgres)
	cd services/api && $(PYTHON) -m pytest tests -q

lint: ## ruff
	ruff check services/api mocks
