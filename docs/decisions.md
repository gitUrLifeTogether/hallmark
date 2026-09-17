# Architecture Decision Records

Format: context → decision → consequences. One entry per significant choice.

## ADR-0001: Pre-commit hooks configured but not yet locally verified

**Context:** This dev machine has no working Python installation (only the Windows Store
alias stub) at the time the repo was scaffolded (2026-09-17). `pre-commit`, `ruff`, `mypy`
and `pytest` all require a real Python 3.12 install.

**Decision:** Scaffold `.pre-commit-config.yaml` and `pyproject.toml` fully per spec now,
so the shape of the toolchain is correct, but defer running `pre-commit install` and the
first `pre-commit run --all-files` until Python 3.12 + uv are installed.

**Consequences:** The first commit is not yet gated by these hooks locally (CI/pre-commit
enforcement starts once Python is installed). No secrets or large files were added by hand;
reviewed manually before commit instead.

## ADR-0002: eslint hook deferred to M4

**Context:** The `web/` frontend (React + Vite + TS) does not exist yet as of the M0
scaffold; an eslint pre-commit hook needs a working eslint config to point at.

**Decision:** Add the eslint pre-commit hook when `web/` is scaffolded in M4, not now.

**Consequences:** TypeScript linting is not enforced until M4. Prettier is already wired
for `web/` files that exist by then.

## ADR-0003: AWS account / Bedrock access status at kickoff

**Context:** The user has an AWS Builder ID but had not confirmed a full AWS account with
Bedrock model access. AWS Builder ID (used for AWS Skill Builder, re:Post, workshops) is a
separate identity system from an AWS account — it does not grant access to AWS services,
billing, IAM, or the AWS Management Console needed to deploy this project (SAM stack,
Bedrock, DynamoDB, Verified Permissions, etc.).

**Decision:** Treat "a real AWS account (root or IAM user) with console/CLI access, a
payment method on file, and Bedrock model access granted for the planner and reader
models in the target region" as a hard M0 blocker owned by the user. Proceed with all
scaffolding, docs, and local-only code that don't require AWS credentials; pause before
any `sam deploy`, Bedrock model access request, or Verified Permissions policy store
creation until the user confirms the account is ready.

**Consequences:** M0's "SAM hello-world Lambda + HTTP API deployed, Amplify placeholder
live" step is blocked until AWS account access is confirmed. Everything else in M0
(repo scaffold, docs skeletons) proceeds now.
