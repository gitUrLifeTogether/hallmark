# Adding a consequential tool

The claim this document has to earn is that adding a new consequential action requires no
edit to the enforcement point or the planner. `send_email` was built this way after
`pay_vendor`, and the steps below are the ones that were actually taken.

If you find yourself editing `pep.py`'s decision flow or `planner.py`'s loop to add a
tool, something has gone wrong in the design rather than in your change.

## The five steps

### 1. Declare the tool

Add a `ToolSpec` to `TOOL_SPECS` in `hallmark/application/agent_tools.py`:

```python
"send_email": ToolSpec(
    "send_email",
    consequential=True,
    handle_required_args=frozenset({"recipient_handle"}),
    cedar_action="send_email",
),
```

`handle_required_args` is the important field. Anything named there can never arrive as a
literal, so the planner cannot type a raw email address or account number in place of a
value whose provenance is known.

### 2. Write the fact checkers

Facts are what the company's own records say, computed in code. Add a function to
`hallmark/application/fact_checkers.py` returning a frozen dataclass:

```python
def compute_email_facts(recipient, attachments, template_confidentiality, company, vendors)
    -> EmailFacts
```

Two rules for anything in here. It must be deterministic, and it must never ask a model
what it thinks. A fact a model can be argued out of is not a fact.

### 3. Build the Cedar request

Add a builder to `hallmark/application/cedar_request_builder.py`. Put the argument labels
in the context with `arg_label(value)`, and read the mandate from the run rather than from
anything the planner supplied:

```python
context={
    "mandate": mandate.to_cedar_context(),
    "recipient": arg_label(recipient),
    "recipientIsInternal": facts.recipient_is_internal,
    ...
}
```

### 4. Write the policies

One `.cedar` file per area in `policies/`, each statement carrying an `@id`. You need at
least a permit, or the action is refused by default, which is the correct behaviour if you
forget.

Then two entries that are easy to miss:

- **`policies/reasons.json`** — a plain-language label and explanation per `@id`. This is
  what the console shows a person, so write it for them and not for a developer.
- **`REASON_PRECEDENCE` in `hallmark/application/pep.py`** — where your policy sits when
  several denials fire at once. Put guarantees no approver can lift above ones that merely
  need a signature. Skipping this means your policy can be masked by a less important one
  (see ADR-0008).

### 5. Add the scenarios

Extend the table in `tests/policies/test_scenarios.py`. For a consequential action, cover
at minimum:

- the happy path,
- each argument carrying untrusted provenance,
- the same cases again with `humanApproved=True`, which is where you decide in public
  whether a person can override your rule,
- any ground-truth fact being false.

## What deliberately has no tool

There is no action for changing a vendor's bank details, and adding one would undo the
central guarantee. An agent can only ever `open_bank_change_review`, which creates work
for a person. Details change through the review service, driven by a human who verified
the change out of band, on a phone number from the vendor master rather than one from the
email asking for the change.

If a future requirement seems to need an agent-writable master data path, that is a design
conversation, not a tool to add quietly.

## Checking your work

```bash
uv run pytest -q tests/           # scenarios, properties, canary, acceptance
uv run ruff check . && uv run mypy hallmark
```

The canary test in `tests/security/` will fail if your tool returns untrusted text to the
planner, which is the mistake easiest to make here. If it fails, the fix is to return a
handle and leave the content in the store, not to strip the text.
