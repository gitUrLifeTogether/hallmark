# Architecture

Two diagrams. The first is what runs; the second is what it was shaped to become. The
difference between them is adapters, not design — which is the claim this document exists
to make checkable.

For the reasoning behind the shape, see [hld.md](hld.md); for the module-level detail,
[lld.md](lld.md).

## What runs today

Everything on one laptop. No cloud account, no bill, no public URL.

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Console — React + Vite, localhost:5173                             │
  │  Runs · Split replay · Lineage · Approvals · Bench · Policies        │
  └──────────┬──────────────────────────────────┬───────────────────────┘
             │ REST + JWT                       │ WebSocket
  ┌──────────▼───────────────┐      ┌───────────▼────────────────────────┐
  │ API Gateway (REST v1)    │      │ Realtime gateway — FastAPI, host   │
  │  Lambda authorizer       │      │  drains the queue, fans out        │
  └──────────┬───────────────┘      └───────────▲────────────────────────┘
             │                                  │
  ┌──────────▼───────────────┐                  │
  │ Lambda — API handlers    │                  │
  └──────────┬───────────────┘                  │
             │                                  │
  ┌──────────▼──────────────────────────────────┴───────────────────────┐
  │  Application services                                               │
  │                                                                     │
  │   planner ──► Strands Agents ──► Ollama on the host   (has tools,   │
  │      │                                                 sees no text)│
  │      │ handles, enums, checked displays                             │
  │      ▼                                                              │
  │   tool wrappers ──► PEP ──► Cedar (cedarpy, in-process)             │
  │      │                                                              │
  │      └────────► reader ──► Ollama  (sees text, has no tools)        │
  └──────────┬──────────────────────────────────┬───────────────────────┘
             │                                  │ events
  ┌──────────▼───────────────┐      ┌───────────▼───────────────────────┐
  │ DynamoDB · S3            │      │ EventBridge bus ──rule──► SQS     │
  │ values, lineage,         │      │                                   │
  │ decisions, runs,         │      └───────────────────────────────────┘
  │ vendors, ledger,         │
  │ approvals                │       All of the above, except the host
  └──────────────────────────┘       processes below, runs on LocalStack,
                                     deployed from one SAM template.
```

**Three processes run on the host rather than in the emulator**, each for a stated reason:

| On the host | Why not in the emulator |
|---|---|
| Ollama | Models need the machine's memory directly. Functions reach it at `host.docker.internal`. |
| Realtime gateway | A managed WebSocket API is not available on the free emulator plan, so a small FastAPI process drains the same SQS queue the deployed rule feeds. |
| Console dev server | Vite. There is no hosting tier to deploy to, and no public URL is required. |

## The security path, which is the part that matters

Every consequential call takes exactly this route. Nothing shortcuts it.

```
  planner calls pay_vendor(vendor_h, account_h, amount_h, invoice_h)
        │
        ▼
  ① structural check ── an argument that must be a handle is not a literal
        │
        ▼
  ② resolve ────────── handles become labelled values; the planner never held content
        │
        ▼
  ③ facts ─────────── computed in code from company records:
        │              accountMatchesVendorMaster, vendorMatchVerified,
        │              isDuplicateInvoice.  No fact is ever asked of a model.
        ▼
  ④ authorise ─────── Cedar, given the provenance of each argument
        │
        ├── permit ──────────────► execute, write the ledger, record lineage
        │
        └── forbid ──► ask again with humanApproved = true
                          ├── permit ──► PENDING_APPROVAL, a person decides,
                          │               facts recomputed before it executes
                          └── forbid ──► HARD_DENIED, nobody can lift it
```

Any exception anywhere on that path produces `ENFORCEMENT_ERROR` and a denial. It never
falls through to execution — sixteen tests exist to prove that, including ones that pair a
deliberately agreeable policy engine with a broken check, so each guard is shown to hold
on its own rather than because the one after it happened to catch the case.

## Where each mechanism lives

| Mechanism | Code |
|---|---|
| Provenance labels | `hallmark/domain/labels.py` |
| Handles and the value store | `hallmark/ports/stores.py`, `hallmark/adapters/` |
| Planner / reader split | `hallmark/application/planner.py`, `reader.py` |
| Declassification by type | `hallmark/domain/declassify.py` |
| Enforcement point | `hallmark/application/pep.py` |
| Policies | `policies/*.cedar` |
| Lineage | `hallmark/domain/lineage.py` |

Dependencies point inward only: the domain knows nothing, ports are interfaces, the
application orchestrates ports, adapters implement them, and handlers are the only place
that constructs anything concrete. `tests/unit/test_architecture.py` enforces it, and it
caught two real violations during the build.

## The target production design

Not provisioned, and marked as such everywhere it appears. It is named here because the
local stack was deliberately built in its shape.

```
  Console (static hosting) ──► API Gateway ──► Lambda ──► Step Functions
                                                             │
                             ┌───────────────────────────────┤
                             ▼                               ▼
                     planner runtime               approval workflow
                     (container image)             (task tokens, timeouts)
                             │
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
      hosted model    hosted policy     DynamoDB · S3
      service         service (Cedar)
                             ▲
                             │ the same .cedar files
```

What each change actually costs:

| Local today | Production | The change |
|---|---|---|
| Ollama | a hosted model service | one adapter behind `PlannerModel` / `ReaderModel` |
| `cedarpy` in-process | a hosted policy service | one adapter behind `Authorizer`; policies unchanged |
| Approval as a conditional write | Step Functions with task tokens | one adapter behind the approval port |
| Host FastAPI gateway | a managed WebSocket API | one adapter; the queue stays |
| Local HMAC JWTs | a managed identity provider | one adapter behind the authenticator |

**The security kernel appears in none of those rows.** That is the whole reason for the
ports, and it is why this document can be checked against the code rather than believed.

## What the local platform does not do

Recorded honestly, with the reasoning in [decisions.md](decisions.md):

- **No Step Functions.** The approval flow is implemented in application code with a
  conditional write, behind the port a state machine would sit behind. The definition in
  `statemachines/` is a design artefact and is not deployed.
- **REST API rather than HTTP API.** The newer service reports a successful deploy on the
  free emulator plan and is then entirely unusable.
- **Shared code is bundled per function, not shipped as a layer.** The emulator attaches a
  layer without making its contents importable.
- **The planner runs in-process, not inside a deployed function.** The network path from a
  function to the model host is proven; packaging the agent SDK into a function is not.
