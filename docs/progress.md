# Progress

A fresh session should read this file plus `git log --oneline -20` before re-reading the
whole repo.

## §0.1 Repository and Git workflow

- Repo already existed on GitHub (`gitUrLifeTogether/hallmark`) and was already cloned to
  `~/Desktop/hallmark` before this session started — **done**, steps 4–5 of §0.1.1 skipped.
- Scaffolding (`.gitignore`, `.gitattributes`, `.editorconfig`, `README.md`, `LICENSE` (MIT),
  `.pre-commit-config.yaml`) — **done**.
- First commit (`chore: scaffold repository`) — **done**, not pushed (push always requires
  asking first, per §0.1.3).

## Current milestone: M0 — Access & skeleton

Done:
- Repo scaffold (see above).
- Directory skeleton per §17 created with placeholder/stub files.
- `docs/hld.md`, `docs/lld.md` first drafts.
- `pyproject.toml`, `template.yaml` skeleton, `api/openapi.yaml` stub.

Blocked / not done (needs the user):
- AWS account confirmation — user has an AWS Builder ID only, which is **not** sufficient
  (see ADR-0003 in `docs/decisions.md`). Needs a real AWS account with console/CLI access
  and a payment method.
- Bedrock model access request for planner + reader models in the target region.
- Verified Permissions policy store creation.
- SAM hello-world Lambda + HTTP API deploy; Amplify placeholder.
- Python 3.12 + uv install on the dev machine (blocks `pre-commit install`, `mypy`,
  `pytest`, `ruff` running locally — see ADR-0001).

## Open questions for the user

- Confirm AWS account is ready (see above) before continuing M0's cloud steps.
- Confirm Python 3.12 + uv installed before M1 (core security kernel needs pytest/mypy/ruff).
