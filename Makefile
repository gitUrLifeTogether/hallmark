# Hallmark — everything runs locally. Nothing here may touch real AWS.
.DEFAULT_GOAL := help
SHELL := /bin/bash

-include .env
export

# --- LOCAL_ONLY guard --------------------------------------------------------
# Refuse to run any AWS-touching target unless the endpoint is a local emulator.
define require_local_endpoint
	@if [ -z "$$AWS_ENDPOINT_URL" ]; then \
		echo "REFUSING: AWS_ENDPOINT_URL is unset. Hallmark is LOCAL_ONLY; copy .env.example to .env."; \
		exit 1; \
	fi; \
	case "$$AWS_ENDPOINT_URL" in \
		http://localhost:*|http://127.0.0.1:*|http://localstack:*|http://host.docker.internal:*) ;; \
		*) echo "REFUSING: AWS_ENDPOINT_URL=$$AWS_ENDPOINT_URL is not a local emulator."; exit 1 ;; \
	esac
endef

.PHONY: help up down deploy-local seed test e2e console spike fmt lint check

help: ## Show available targets
	@echo "Hallmark local development targets:"
	@sed -n 's/^\([a-z][a-z0-9-]*\):[^#]*## /  \1 -- /p' $(MAKEFILE_LIST)

up: ## Start LocalStack and wait for it to become healthy
	@if [ -z "$$LOCALSTACK_AUTH_TOKEN" ]; then echo "REFUSING: LOCALSTACK_AUTH_TOKEN unset (see .env.example)."; exit 1; fi
	docker compose up -d localstack
	@echo "Waiting for LocalStack..."
	@for i in $$(seq 1 30); do \
		curl -sf http://localhost:4566/_localstack/health >/dev/null && echo "LocalStack healthy." && exit 0; \
		sleep 3; \
	done; echo "LocalStack did not become healthy in 90s."; exit 1

down: ## Stop LocalStack
	docker compose down

deploy-local: ## Build and deploy the SAM stack to LocalStack (idempotent)
	$(require_local_endpoint)
	samlocal build
	samlocal deploy --no-confirm-changeset --no-fail-on-empty-changeset --resolve-s3

seed: ## Load fixtures into LocalStack
	$(require_local_endpoint)
	uv run python -m fixtures.seed

test: ## Unit + property + policy tests (in-memory adapters, no Docker needed)
	uv run pytest -q tests/unit tests/property tests/policies

e2e: ## End-to-end tests against LocalStack
	$(require_local_endpoint)
	uv run pytest -q tests/e2e

spike: ## Run the local platform feasibility spike
	$(require_local_endpoint)
	uv run python scripts/spike.py

console: ## Run the console dev server at localhost:5173
	cd web && npm run dev

fmt: ## Format
	uv run ruff format .

lint: ## Lint and type-check
	uv run ruff check .
	uv run mypy hallmark

check: fmt lint test ## Everything before a commit
