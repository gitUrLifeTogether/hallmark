"""Turn a finished run into the shapes the console renders.

The console had one hardcoded module behind Run, Lineage and Evidence, so it could only
ever show a run that existed when the bundle was built. This builds the same shapes from
what a run actually recorded, which is what lets a submitted email appear on every screen
rather than only on the one that submitted it.

Nothing here decides anything. It reads what the enforcement point and the stores already
hold and reshapes it; a console that re-derived a verdict would eventually disagree with
the system it is meant to be reporting on.
"""

from __future__ import annotations

from typing import Any

from hallmark.application.safe_render import render_email
from hallmark.domain.labels import TRUSTED_SOURCES
from hallmark.ports.repositories import InboxEmail

#: Facts worth showing beside a decision, in the order a reader wants them.
_FACT_ORDER = (
    "accountMatchesVendorMaster",
    "vendorMatchVerified",
    "isDuplicateInvoice",
    "amountPaise",
)

#: Which fact explains which refusal, so the console can mark the decisive one.
_DECISIVE_FOR = {
    "ACCOUNT_NOT_FROM_VENDOR_MASTER": "accountMatchesVendorMaster",
    "VENDOR_NOT_VERIFIED": "vendorMatchVerified",
    "DUPLICATE_INVOICE": "isDuplicateInvoice",
    "ABOVE_AUTO_APPROVE_LIMIT": "amountPaise",
    "ABOVE_MANDATE_CAP": "amountPaise",
}


def _labelled(value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "handle": value.handle,
        "sources": sorted(str(s) for s in value.sources),
        "trusted": value.sources <= TRUSTED_SOURCES,
    }
    if getattr(value, "declassified", False) and getattr(value, "display", None):
        out["display"] = value.display
    return out


def _decision_view(record: Any, values: Any, run_id: str, email_id: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for name, handle in (record.args_handles or {}).items():
        resolved = values.get(run_id, handle)
        if resolved is not None:
            args[name] = _labelled(resolved)

    decisive = _DECISIVE_FOR.get(str(record.reason_code))
    facts = [
        {"name": name, "value": record.facts[name], "decisive": name == decisive}
        for name in _FACT_ORDER
        if name in (record.facts or {})
    ]

    return {
        "decisionId": record.decision_id,
        "emailId": email_id,
        "tool": record.tool,
        "outcome": str(record.outcome),
        "reasonCode": str(record.reason_code),
        "determiningPolicies": list(record.determining_policies or ()),
        "args": args,
        "facts": facts,
        "at": record.created_at,
    }


def _lineage_view(values: Any, lineage: Any, run_id: str, decisions: list[dict[str, Any]]) -> Any:
    """Nodes and edges for the graph, laid out by how far a value is from its source."""
    nodes: dict[str, dict[str, Any]] = {}
    for value in values.for_run(run_id):
        nodes[value.handle] = {
            "handle": value.handle,
            "label": str(value.vtype),
            "kind": "source" if not value.parents else "value",
            "sources": sorted(str(s) for s in value.sources),
            "depth": 0,
        }

    edges = [
        {
            "from": edge.source_handle,
            "to": edge.target_handle,
            "kind": str(edge.kind),
            "label": edge.label or "",
        }
        for edge in lineage.edges_for_run(run_id)
    ]

    # Depth by longest path from a root, so derived values sit right of what they came from.
    for _ in range(len(edges)):
        changed = False
        for edge in edges:
            source, target = nodes.get(edge["from"]), nodes.get(edge["to"])
            if source and target and target["depth"] <= source["depth"]:
                target["depth"] = source["depth"] + 1
                changed = True
        if not changed:
            break

    for decision in decisions:
        depth = 1 + max(
            (
                nodes[a["handle"]]["depth"]
                for a in decision["args"].values()
                if a["handle"] in nodes
            ),
            default=0,
        )
        nodes[decision["decisionId"]] = {
            "handle": decision["decisionId"],
            "label": decision["tool"],
            "kind": "decision",
            "sources": [],
            "depth": depth,
        }
        edges.extend(
            {"from": a["handle"], "to": decision["decisionId"], "kind": "arg", "label": name}
            for name, a in decision["args"].items()
        )

    return list(nodes.values()), edges


def _email_view(email: InboxEmail) -> dict[str, Any]:
    """The email as the console may show it: sanitised, with hidden passages named."""
    body = email.body
    if email.hidden_text:
        body += f"<span style='display:none'>{email.hidden_text}</span>"
    for attachment in email.attachments:
        if attachment.text:
            body += f"<span style='display:none'>{attachment.text}</span>"

    rendered = render_email(body)
    return {
        "emailId": email.email_id,
        "subject": email.subject,
        "sender": email.sender,
        "dkim": "pass" if email.dkim_pass else "fail",
        "html": rendered.html,
        "hidden": [{"technique": h.technique, "text": h.text} for h in rendered.hidden],
    }


def build_run_detail(
    run_id: str,
    email: InboxEmail,
    values: Any,
    lineage: Any,
    decisions: Any,
    ledger: Any,
) -> dict[str, Any]:
    """Everything the console needs to show one run on every screen."""
    records = decisions.for_run(run_id)
    views = [_decision_view(r, values, run_id, email.email_id) for r in records]
    nodes, edges = _lineage_view(values, lineage, run_id, views)

    outcomes = [v["outcome"] for v in views]
    return {
        "runId": run_id,
        "decisions": views,
        "lineage": {"nodes": nodes, "edges": edges},
        "email": _email_view(email),
        "counts": {
            "executed": outcomes.count("EXECUTED"),
            "pendingApproval": outcomes.count("PENDING_APPROVAL"),
            "denied": outcomes.count("DENIED"),
            "paid": len(ledger.entries()),
        },
    }
