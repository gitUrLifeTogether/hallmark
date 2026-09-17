# Progress

A fresh session should read this file plus `git log --oneline -20` before re-reading the
whole repo.

## Track: Build It (CLAUDE.md §0.0) — nothing touches real AWS

Local stack: Strands + Ollama, Cedar via `cedarpy` in-process, SAM + LocalStack.
See ADR-0003. Bedrock / Verified Permissions / Cognito / Amplify are **not provisioned**.

## §0.1 Repository and Git workflow

- Repo already existed on GitHub (`gitUrLifeTogether/hallmark`) and was already cloned to
  `~/Desktop/hallmark` — **done**, steps 4–5 of §0.1.1 skipped, do not re-create it.
- Scaffolding + first commit (`chore: scaffold repository`) — **done**. Nothing pushed yet;
  pushing always requires asking first (§0.1.3).

## M0 — Toolchain, spike & skeleton

**Toolchain — all installed and verified:**
Python 3.12.10, uv, Node 24.19, npm 11.17, Docker 29.7.2 (healthy, Linux engine),
Ollama 0.34.1, SAM CLI 1.166.2, aws CLI 2.36.47, samlocal, awslocal, git 2.55, gh 2.101.
Cedar CLI intentionally skipped (needs Rust; `cedarpy` validates schemas in-process).

**Models pulled:** `qwen3:4b` (planner), `qwen3:1.7b` (reader). See ADR-0004.

**Done:**
- `hallmark/config.py` — `LOCAL_ONLY` guard + `hallmark/domain/errors.py`; **19/19 tests
  passing** (`tests/unit/test_config_guard.py`).
- `.env.example` + `.env` (gitignored, token in place), `docker-compose.yml` (LocalStack
  pinned `4.9.1`), `Makefile` with its own `LOCAL_ONLY` guard.
- `spike/template.yaml` — the five-check spike stack (written; not yet deployed).
- LocalStack running and healthy on the free token; **community edition**, all needed
  services available.
- Spike checks **3 (DynamoDB)**, **5 (EventBridge→SQS)** and **1a (cedarpy on host)** PASS.
  Full results, pass and fail, in ADR-0005.

**✅ SPIKE COMPLETE — all five checks PASS. Go/no-go: GO on LocalStack.**
The §0.0.6 fallback is **not** needed. Checks 1b (cedarpy in a Lambda container), 4 (Step
Functions `waitForTaskToken` end-to-end) and 2 (Lambda→Ollama via `host.docker.internal`)
all pass; full evidence and free-RAM readings in ADR-0005.
`OLLAMA_KEEP_ALIVE=0` + `OLLAMA_MAX_LOADED_MODELS=1` set for headroom (ADR-0007).

**Carried into M3 as unproven (do not assume these work):**
- `samlocal build && samlocal deploy` (CloudFormation) against LocalStack — the spike
  created resources directly via the `aws` CLI to conserve memory.
- Packaging the **Strands Agents SDK** into the planner Lambda (check 2 used stdlib
  `urllib`, proving the network path only).

**Not started:** console placeholder at `localhost:5173`; `pre-commit install`;
full §17 directory skeleton.

## Gotchas that will bite again

- `PERSISTENCE: 0` — LocalStack state is lost on restart; `make seed` must be idempotent.
- On Windows, `aws lambda invoke --payload` with inline escaped JSON fails with a utf-8
  decode error. **Always pass `fileb://<file>`.**
- Prefer the compiled `aws --endpoint-url` over `awslocal` (ADR-0006).

## M1 - Core security kernel: COMPLETE

Domain (pure, no I/O): `labels.py`, `values.py`, `identifiers.py`, `declassify.py`,
`lineage.py`, `mandate.py`, `tools.py`, `errors.py`.
Ports + in-memory adapters for every one. Cedar policies (9, with `@id` names) evaluated
through `cedarpy`. Enforcement point, fact checkers, request builder, quarantined reader.
Hero fixtures: fictional company, 6 vendors, 20-email inbox with both attacks.

**Acceptance gate passes**, deterministically and with no model in the loop:

| Outcome | Count | Which |
|---|---|---|
| EXECUTED | 16 | the routine invoices |
| PENDING_APPROVAL | 1 | email-17, above the auto-approve limit |
| DENIED | 3 | email-18 duplicate, email-19 bank-change attack, email-20 exfiltration |

email-19 is hard-denied by `pay-account-must-be-master` (`ACCOUNT_NOT_FROM_VENDOR_MASTER`)
and opens a bank-change review. email-20 is denied by `email-confidential-internal-only`.

**136 tests pass**; ruff and `mypy --strict` clean; 94% coverage on domain + application.
Includes 35 Cedar scenarios, Hypothesis property tests for the label algebra, reader
verification tests, fail-closed tests and a determinism test.

## Not started

Console placeholder at `localhost:5173`; `pre-commit install`; `make` is not installed on
this machine, so Makefile targets are unverified.

## Next steps

1. M2 - the agent: Strands planner on Ollama in per-email episodes, reader with
   JSON-schema output, handle-based tool wrappers, and the canary isolation test.
2. Install `make`, run `pre-commit install`, add the console placeholder.
3. Validate `samlocal` + CloudFormation early in M3.
