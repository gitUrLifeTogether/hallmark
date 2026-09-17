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

## Next steps

1. M1 — core security kernel (labels, declassify, lineage, PEP, ≥30 Cedar scenario tests).
2. Console placeholder + `pre-commit install` + full §17 skeleton (M0 leftovers).
3. Validate `samlocal` + CloudFormation early in M3.
