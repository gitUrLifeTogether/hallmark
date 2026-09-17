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

**⏸️ HALTED — awaiting a decision from the user:**
Spike checks **1b** (cedarpy inside Lambda), **2** (Lambda→Ollama via
`host.docker.internal`) and **4** (Step Functions `waitForTaskToken`) are **not run**. The
host hit its memory ceiling first: 0.5 GB free RAM, commit 23.2/24.8 GB, `awslocal`
segfaulting. Per standing instruction, stopped rather than pushing through swapping.
These checks are **unproven, not failed** — no §0.0.6 fallback decision has been made.

**Not started:** console placeholder at `localhost:5173`; `pre-commit install`;
full §17 directory skeleton.

## Next steps

1. Free memory (stop the unrelated `trueforge` stack; close Brave/VS Code), then re-run
   spike checks 1b, 2, 4.
2. If they fail twice with memory free → propose the §0.0.6 fallback (SAM CLI local +
   DynamoDB Local + local workflow engine behind the `RunOrchestrator`/`ApprovalGateway`
   ports). Only adapters change; the hexagonal core, Cedar, Strands and Ollama are the same.
3. Then M1 — core security kernel (labels, declassify, lineage, PEP, ≥30 Cedar tests).
