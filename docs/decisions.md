# Architecture Decision Records

Format: context → decision → consequences. One entry per significant choice.

## ADR-0001: Pre-commit hooks configured before the toolchain existed

**Context:** When the repo was first scaffolded (2026-09-17) the dev machine had no working
Python install, so `pre-commit`, `ruff`, `mypy` and `pytest` could not run.

**Decision:** Scaffold `.pre-commit-config.yaml` and `pyproject.toml` fully per spec, and
run them once Python 3.12 landed.

**Consequences:** Python 3.12.10 + uv are now installed and `pytest` runs (19/19 on the
`LOCAL_ONLY` guard). `pre-commit install` still to be run.

## ADR-0002: eslint hook deferred to M4

**Context:** `web/` does not exist yet; an eslint hook needs a config to point at.

**Decision:** Add the eslint pre-commit hook when `web/` is scaffolded in M4.

**Consequences:** TypeScript linting is not enforced until M4.

## ADR-0003: Build It track — nothing touches real AWS (supersedes the earlier AWS-account plan)

**Context:** An earlier version of this ADR treated "get an AWS account with a card" as an
M0 blocker. `CLAUDE.md` §0.0 now defines the **Build It** track: the user cannot use paid
AWS services or provide a card. An AWS Builder ID is a training/community identity and
grants no access to AWS services, so it would not have unblocked anything either.

**Decision:** Build entirely on the local stack of §0.0.2 — Strands Agents with local
**Ollama** models, **Cedar via `cedarpy` evaluated inside the Lambda functions**, **SAM +
LocalStack**. Bedrock, Verified Permissions, Cognito, Amplify, X-Ray and CloudWatch are
**not provisioned**; §12 stays in the docs as the target production architecture, marked
as such. Verified Permissions remains reachable later purely by swapping the `Authorizer`
port's adapter.

**Consequences:** No cloud bill and no public URL; the project competes in Build It, not
Ship It. The AVP/`cedarpy` parity test is deferred (§0.0.7) since only one backend exists.
Enforced in code by the `LOCAL_ONLY` guard (`hallmark/config.py`), in tooling by the
`Makefile` guard, and by using dummy credentials only.

## ADR-0004: Models chosen for an 8 GB machine

**Context:** Dev machine measured at **7.77 GB RAM, Intel UHD integrated graphics (no
discrete GPU), 8 logical cores, 72 GB free disk**. This is the 8 GB row of §0.0.4.

**Decision:** Planner `qwen3:4b` (2.5 GB, tool calling), reader `qwen3:1.7b` (1.4 GB,
structured JSON, no tools). Both pulled 2026-09-17. Bench concurrency 1; bench runs
in-process rather than on LocalStack (§0.0.5.4).

**Consequences:** Lower planner utility than the 32 GB row would give. **This does not
weaken any security property** — labels, the PEP, Cedar and the canary test hold with any
model; a weaker model only lowers utility (§0.0.4). Say so in README and video.

## ADR-0005: M0 feasibility spike — partial results, halted on memory pressure

Run 2026-09-17 against LocalStack **4.9.1, community edition**, free auth token accepted.
Recorded pass *and* fail as instructed.

| # | Check | Result | Evidence |
|---|---|---|---|
| — | LocalStack starts on the free token | ✅ PASS | container healthy; `edition: community` |
| — | Required services available | ✅ PASS | `dynamodb, lambda, s3, events, sqs, stepfunctions, apigateway, iam, logs` all `available` on the free plan |
| 3 | DynamoDB table write + read | ✅ PASS | `put-item` then `get-item` returned `{"pk":"spike#1","note":"hallmark-m0"}` |
| 5 | EventBridge rule → SQS → host script | ✅ PASS | `put-events` `FailedEntryCount=0`; host received the full envelope incl. `detail.policyId=pay-account-must-be-master` |
| 1a | `cedarpy` evaluates a policy (host Python) | ✅ PASS | legit payment `Decision.Allow`; email-derived account `Decision.Deny` — the core guarantee |
| 1b | `cedarpy` evaluated **inside a Lambda** | ⏸️ NOT RUN | needs Lambda containers — halted, see below |
| 2 | Lambda → Ollama on host via `host.docker.internal` | ⏸️ NOT RUN | needs Lambda container + 2.5 GB model resident |
| 4 | Step Functions `waitForTaskToken` | ⏸️ NOT RUN | needs Lambda containers |

**Why halted:** the host hit its memory ceiling before checks 1b/2/4 could run —
**0.5 GB free physical RAM, commit charge 23.2 GB against a 24.8 GB limit (94%), 4.7 GB of
pagefile in use.** The first concrete symptom was `awslocal` **segfaulting** on every
invocation (its Python wrapper could not allocate). The user's standing instruction was to
stop rather than push through swapping, so the spike was halted rather than continued.
Checks 1b/2/4 are **unproven, not failed** — no conclusion either way.

**Contributing factor:** an unrelated `trueforge` stack (truefoundry-server 1.71 GB image +
postgres + redis) was running throughout and is still resident.

**Decision:** Do not conclude on §0.0.6 yet. The three services those checks depend on are
confirmed *available*; what is unproven is whether **this machine** can hold LocalStack +
Lambda containers + a 2.5 GB model at once. Re-run 1b/2/4 after freeing memory before
deciding whether to fall back.

## ADR-0006: Use `aws --endpoint-url` rather than `awslocal`

**Context:** `awslocal` (a Python wrapper around the AWS CLI) segfaulted on every call under
memory pressure. The compiled `aws` CLI v2 with an explicit `--endpoint-url` worked on the
same operations immediately afterwards.

**Decision:** Prefer `aws --endpoint-url=$AWS_ENDPOINT_URL` in scripts and Makefile targets.
`samlocal` is still used for deploys (it has no equivalent flag).

**Consequences:** One fewer Python process per CLI call, which matters on this machine. The
`LOCAL_ONLY` guard in the `Makefile` already validates `AWS_ENDPOINT_URL`, so pointing the
real CLI at it is no less safe than `awslocal`.
