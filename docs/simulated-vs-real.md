# What is real and what is simulated

A demo that blurs this line is worth nothing, so here it is explicitly. The short version:
**the security mechanism is real and the world it operates on is invented.**

## Real

These are working implementations, not mock-ups. If they were wrong, the demonstration
would not work.

| | Notes |
|---|---|
| Provenance labels and the join algebra | Property-tested over randomly generated derivation trees |
| Declassification by type | Per-type validators; prose and addresses are never shown |
| The enforcement point | Resolve, compute facts, authorise, act — failing closed throughout |
| Cedar policies | Real Cedar, evaluated by `cedarpy`, the same engine and the same `.cedar` files a hosted policy service would load |
| The lineage graph | Actually recorded, actually queried, actually drawn |
| Field-in-source verification | Real normalisation, including zero-width and Unicode tag stripping |
| The safe renderer | Real sanitisation via a vetted library, with 24 evasion payloads tested structurally |
| Approval flow | Real role limits, a real conditional write, and a real re-authorisation |
| The API | Real HTTP over a deployed stack, with verified tokens |
| The measurements | Every number in the README and bench report is produced by a script in this repository |

## Simulated

| | What it stands in for |
|---|---|
| Kestrel Components and its six vendors | A real company's supplier master |
| GSTINs, bank accounts, IFSC codes | Format-valid, entirely invented |
| The ledger and every rupee | A payments system. No money exists; nothing is ever sent anywhere |
| The inbox | Fixture emails in S3 rather than a mail server |
| Demo users and their tokens | An identity provider. Real HMAC signing, but no user directory |
| DKIM results | Fixture fields, not real signature verification |

**No real bank, payment, or email service is contacted at any point.** The `LOCAL_ONLY`
guard makes that structural rather than a matter of care: every client is constructed
through one factory that refuses any endpoint outside a local emulator, and a typo in the
switch leaves the guard on.

## The platform

The infrastructure is real AWS *shapes* running on a local emulator: CloudFormation,
Lambda, DynamoDB, S3, EventBridge, SQS and API Gateway, described in one SAM template. The
code is production-shaped — handlers are composition roots, adapters sit behind ports — but
it has never run against a cloud account, and there is no public URL.

Two things differ from what a cloud deployment would use, and both are recorded in
`decisions.md`:

- **REST API rather than HTTP API**, because the emulator does not provide the newer
  service on its free plan. A deploy of it reports success and is entirely unusable.
- **The realtime gateway runs on the host** rather than as a managed WebSocket API, for the
  same reason. It drains the same queue the deployed rule feeds.

Shared code is bundled per function instead of shipped as a Lambda layer, because the
emulator attaches a layer without making its contents importable.

## The live run

The console's **Live run** view is genuinely live. An email typed into it is submitted to
the deployed API, recorded, and announced on the event bus; a host worker picks it up and
processes it with the real model-backed planner through the same tools, enforcement point
and policies as everything else. The verdict shown is the one the enforcement point
recorded, and the steps appear over the same WebSocket the gateway feeds.

Two parts of it are simulated, and neither is load-bearing:

- **The DKIM result.** A typed-in address has no signature to verify, so it passes only
  when the sender's domain is exactly a vendor's registered domain. That is what a real
  check would return for a genuine sender, and it makes a lookalike domain fail. It feeds
  `vendorMatchVerified`, which a human can override; the account rule, which nobody can
  override, does not consult it.
- **The vendor master and ledger** are the same fixtures as everywhere else.

The rest of the console still renders a recorded run. Live run and Approvals talk to the
deployed API; Run, Split replay, Bench, Lineage, Evidence and Policies do not.

## The models

Both the planner and the reader run on a local open-weight model through Ollama. On the
development machine — 8 GB RAM, no discrete GPU — both roles use `qwen3:1.7b`.

**The bench numbers do not involve a model at all.** Both configurations are driven by a
deterministic planner following a fixed procedure. That is deliberate: it isolates the
enforcement layer from model variance, and the guarantee under test does not depend on the
model. It also means those numbers say nothing about how a language model behaves.

A separate model-backed run is recorded in `decisions.md`. In it the planner *attempted*
the bank-change payment and was refused by the account rule. That run is the more
interesting evidence, precisely because the model was fooled and the outcome did not
depend on it.

**Security never depends on model quality.** The labels, the enforcement point, the
policies and the canary test hold with any model. A weaker model lowers utility, not
safety.

## What has not been proven

- **Scale.** One tenant, one fixture company, twenty emails. Keys are tenant-prefixed and
  the episode carries no cross-email state, so the shape suits concurrency, but that is a
  design property rather than a measurement.
- **Latency.** The figures taken during development were contaminated by other work
  competing for the CPU and are not published. Nothing here should be quoted as a
  performance number.
- **A hosted policy service.** The `Authorizer` port has one implementation. The parity
  test between two backends is future work.
- **The agent SDK inside a deployed function.** Runs are driven in-process; the network
  path from a function to the model host is proven, the packaging is not.
