# Low-Level Design

## Layers, and what may import what

```
domain/        pure. no I/O, no AWS, no model SDKs, no framework
ports/         typing.Protocol interfaces
application/   use cases orchestrating ports
adapters/      one per outside system
handlers/      composition roots; the only place clients are constructed
```

Dependencies point inward only. `domain/` imports nothing from the other three, which is
why the label algebra can be property-tested in milliseconds and why the security kernel
is provably free of infrastructure.

## Domain

| Module | Holds |
|---|---|
| `labels.py` | `Source`, `Confidentiality`, `ValueType`; `join_sources`, `is_trusted` |
| `values.py` | `Labeled[T]` and `derive`, the only way to make a value from other values |
| `identifiers.py` | `Gstin`, `Ifsc`, `AccountNumber`, `InvoiceNumber`, `Domain`, `EmailAddress` |
| `declassify.py` | per-type validators deciding what the planner may see |
| `lineage.py` | the provenance graph and ancestor queries |
| `mandate.py` | the user's confirmed scope |
| `tools.py` | `ToolSpec`, and the fixed enums the planner may receive |
| `errors.py` | `HallmarkError` and its children |

Two details carry weight:

**`AccountNumber` masks itself.** `__str__` and `__repr__` return `XXXXXXXX3456`, so an
account cannot reach a log line or a traceback through ordinary string formatting.
Equality still compares the full value, so matching against the vendor master stays exact.

**`derive` is the only join.** Sources union, confidentiality takes the maximum, parents
are recorded. There is no function anywhere that removes a source, and the property tests
assert that a trusted result implies every input was trusted.

## Ports

`ValueStore`, `LineageStore`, `DecisionStore`, `Authorizer`, `VendorRepository`,
`LedgerRepository`, `InboxRepository`, `IdGenerator`, `Clock`, and `ReaderModel`.

Every one has an in-memory implementation in `adapters/memory/`, which is what the whole
test suite runs on. That is deliberate: if the kernel needed Docker to be tested, the tests
would be slow enough that people would stop running them.

## Application

| Module | Responsibility |
|---|---|
| `agent_tools.py` | the tool surface; resolves handles, returns only safe shapes |
| `pep.py` | resolve → facts → Cedar → act, failing closed |
| `fact_checkers.py` | deterministic checks against company records |
| `cedar_request_builder.py` | argument labels and facts into a Cedar request |
| `reader.py` | field-in-source verification and normalisation |
| `planner.py` | Strands wiring, one episode per email |
| `scripted_run.py` | deterministic planner for acceptance and tests |

### The enforcement sequence

```
resolve handles            → literal where a handle is required is refused outright
compute facts              → from the vendor master and ledger, never from a model
build request              → mandate read from the run, never from the planner
authorize                  → allow → execute
                             deny  → ask again with humanApproved=true
                                     allow → escalate to a person
                                     deny  → refuse outright
record                     → decision, arguments, facts, deciding policies
```

The second question is what separates "a person can approve this" from "nobody can". It is
the reason `pay-account-must-be-master` has no `humanApproved` clause: asking again changes
nothing, so the refusal is final by construction rather than by convention.

### Reporting a reason

Several `forbid` policies can fire at once and the engine gives no ordering. The reason
surfaced comes from `REASON_PRECEDENCE`, with guarantees no approver can lift ranked above
those that merely need a signature. Without it the bank-change attack reported
`VENDOR_NOT_VERIFIED`, which is true but implies a person could wave it through (ADR-0008).

### The call budget

`AgentTools.start_episode(budget)` resets a counter; every planner-callable method spends
one unit and returns a refusal once the budget is gone. Enforced in code, not in the
prompt, because a model that has lost the thread is precisely the one that will not honour
an instruction to stop. An exhausted budget denies a payment like any other refusal.

## State machines

- Run: `DRAFT → AWAITING_MANDATE → RUNNING → COMPLETED | FAILED`
- Approval: `PENDING → APPROVED | REJECTED | EXPIRED`
- Review: `OPEN → COMPLETED`

Each transition goes through one function that checks the allowed-transition table and
uses a conditional write, so two concurrent approvals cannot both win.

## Error model

`HallmarkError` → `ValidationError`, `ConfigurationError`, `EnforcementError`,
`PolicyDenied`, `NotFound`, `Conflict`, `DependencyError`.

Mapped to `ReasonCode` enums at the boundary. Nothing derived from untrusted content ever
appears in an error message the planner or an API client can see.

## Access patterns

| Store | Pattern | Key |
|---|---|---|
| Values | fetch by handle within a run | `(run_id, handle)` |
| Lineage | ancestors of a handle | edges by `run_id`, index on target |
| Decisions | list for a run | `(run_id, decision_id)` |
| VendorMaster | by GSTIN, by id, versioned | `(vendor_id, version)` |
| Ledger | has this invoice been paid | `(vendor_id, invoice_number)` |

No scans. The lineage traversal is cycle-safe; provenance graphs are acyclic by
construction, but a corrupted store should not hang the console.

## Testing

| Kind | Where | What it protects |
|---|---|---|
| Property | `tests/property/` | the label algebra, over random derivation trees |
| Policy scenarios | `tests/policies/` | every guarantee, as a table |
| Canary isolation | `tests/security/` | untrusted text never reaching the planner |
| Unit | `tests/unit/` | domain types, tool surface, budget, fail-closed |
| Acceptance | `tests/unit/test_hero_run_scripted.py` | the whole hero run, deterministically |
| Model-backed | `tests/e2e/` | opt-in (`-m model`), needs Ollama |

The canary suite includes a test that the detector itself can catch a planted leak. A check
that cannot fail proves nothing.
