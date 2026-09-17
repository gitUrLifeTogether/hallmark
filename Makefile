# Hallmark — everything runs locally. Nothing here may touch real AWS.
.DEFAULT_GOAL := help
SHELL := /bin/bash

-include .env
export

# Scripts import the package from the repository root.
export PYTHONPATH := $(CURDIR)

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

# samlocal's own launcher runs whatever `python` is first on PATH instead of the
# interpreter in its tool environment, so boto3 appears missing. Call the shim with its
# own interpreter. UV_LINK_MODE=copy is needed wherever the tree is on OneDrive.
# samlocal's own launcher runs whatever `python` is first on PATH instead of the
# interpreter in its tool environment, so boto3 appears missing. Call the shim with its
# own interpreter. UV_LINK_MODE=copy is needed wherever the tree is on OneDrive.
SAMLOCAL_PY := $(APPDATA)/uv/tools/aws-sam-cli-local/Scripts/python.exe
SAMLOCAL_SHIM := $(USERPROFILE)/.local/bin/samlocal
SAMLOCAL := UV_LINK_MODE=copy "$(SAMLOCAL_PY)" "$(SAMLOCAL_SHIM)"

# Build outside the repository. A file sync client holds handles open inside it, the
# build then fails with "Access is denied", and the deploy that follows happily ships the
# PREVIOUS artifacts while reporting success. Building elsewhere avoids the whole class.
SAM_BUILD_DIR := $(TEMP)/hallmark-sam-build

deploy-local: ## Build and deploy the stack to the local emulator
	$(require_local_endpoint)
	uv run python scripts/build_bundle.py
	$(SAMLOCAL) build --template template.yaml --build-dir "$(SAM_BUILD_DIR)"
	@# Only deploy the template the build just produced, never a stale one.
	$(SAMLOCAL) deploy --template-file "$(SAM_BUILD_DIR)/template.yaml" 		--stack-name hallmark --no-confirm-changeset --no-fail-on-empty-changeset 		--resolve-s3 --capabilities CAPABILITY_IAM

redeploy-local: ## Delete and recreate the stack (needed after a key schema change)
	$(require_local_endpoint)
	aws --endpoint-url=$$AWS_ENDPOINT_URL cloudformation delete-stack --stack-name hallmark
	sleep 10
	$(MAKE) deploy-local

env: ## Print the stack outputs as shell exports, for tests and scripts
	@uv run python scripts/stack_env.py

seed: ## Load fixtures into LocalStack
	$(require_local_endpoint)
	@# Table and bucket names come from the stack that exists, as in e2e. Without this
	@# the target fails on a fresh emulator, which is exactly when it is needed.
	eval "$$(uv run python scripts/stack_env.py)" && 		uv run python -m fixtures.seed

test: ## Unit + property + policy tests (in-memory adapters, no Docker needed)
	uv run pytest -q tests/unit tests/property tests/policies

e2e: ## Contract and end-to-end tests against the deployed stack
	$(require_local_endpoint)
	@# Table names come from the stack that exists, never from a guess.
	eval "$$(uv run python scripts/stack_env.py)" && 		uv run pytest -q -m localstack tests/contract tests/e2e

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
