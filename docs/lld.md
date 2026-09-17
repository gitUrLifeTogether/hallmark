# Low-Level Design

First draft — kept current as milestones land (§0.2.1.14). Expand with class diagrams,
state machines and error model as M1/M2 land.

## Ports (`hallmark/ports/`, `typing.Protocol`)

| Port | Purpose |
|---|---|
| `ValueStore` | persist/retrieve `Labeled[T]` values by handle |
| `LineageStore` | persist lineage nodes/edges |
| `DecisionStore` | persist PEP decisions |
| `Authorizer` | `is_authorized(request) -> Decision`; `avp` and `local` (cedarpy) adapters |
| `PlannerModel` / `ReaderModel` | Bedrock model invocation, kept separate so the reader never gets tools |
| `EventPublisher` | EventBridge / WebSocket fanout |
| `ApprovalGateway` | Step Functions task token start/resolve |
| `VendorRepository` / `LedgerRepository` / `InboxRepository` | mock enterprise system repositories |
| `Clock` / `IdGenerator` | testability seams |

## Adapters (`hallmark/adapters/`)

`dynamodb/`, `avp/`, `cedar_local/`, `bedrock/`, `eventbridge/`, `stepfunctions/`, `s3/`,
`memory/` (in-memory implementations of every port, used for fast unit tests and local
runs without AWS credentials).

## Access patterns (DynamoDB, §0.2.1.6) — to confirm against §13 before table creation

| Table | Pattern | Key |
|---|---|---|
| `Runs` | get/list runs for a user | `runId` |
| `Values` | get a labeled value by handle within a run | `runId` / `handle` |
| `Lineage` | ancestor subgraph of a handle | `runId` / `edgeId`, GSI on `to` |
| `Decisions` | list decisions for a run | `runId` / `decisionId` |
| `PendingActions` | get/list pending approvals | `approvalId` |
| `VendorMaster` | current + versioned vendor record | `vendorId` / `version` |

No `Scan` in application code (§0.2.1.6). Full table list in `CLAUDE.md` §13.

## State machines (enums with allowed-transition tables, §0.2.2.6)

- Run status: `DRAFT → AWAITING_MANDATE → RUNNING → COMPLETED | FAILED`.
- Approval status: `PENDING → APPROVED | REJECTED | EXPIRED`.
- Review status: `OPEN → COMPLETED`.

Each transition goes through one function per entity that enforces the table and uses a
conditional write (§0.2.1.4).

## Error model

`HallmarkError` → `ValidationError`, `EnforcementError`, `PolicyDenied`, `NotFound`,
`Conflict`, `DependencyError`. Mapped to `reason_code` enums and HTTP status codes only at
the boundary (handlers); never leak stack traces or untrusted text to the planner or API
clients (§0.2.2.7).

## Design patterns in use (name in docstrings where applied, §0.2.2.8)

Decorator (PEP wrapping consequential tools), Strategy (`Authorizer` backends, model
providers), Adapter (AWS integrations), Repository (vendor/ledger/inbox/values/lineage),
Registry/Factory (`ToolRegistry`), Chain of responsibility (`FactChecker`s), Builder
(`CedarRequestBuilder`).

## Open items

- Full module/class diagrams once `hallmark/domain` and `hallmark/application` land (M1).
- Finalize GSIs against real query patterns before M3 table creation.
