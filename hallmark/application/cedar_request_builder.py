"""Turning resolved arguments and facts into a Cedar request.

The mandate in the context is read from storage, never from the planner. If the planner
could state its own spending limit, the limit would mean nothing.
"""

from __future__ import annotations

from typing import Any

from hallmark.application.fact_checkers import EmailFacts, PaymentFacts
from hallmark.domain.mandate import Mandate
from hallmark.domain.values import Labeled
from hallmark.ports.authorizer import AuthzRequest


def arg_label(value: Labeled[Any]) -> dict[str, Any]:
    """The provenance of one argument, as Cedar sees it."""
    return {"sources": sorted(str(s) for s in value.sources), "trusted": value.trusted}


def build_payment_request(
    run_id: str,
    user_id: str,
    vendor_id: str,
    vendor_status: str,
    mandate: Mandate,
    amount: Labeled[Any],
    account: Labeled[Any],
    facts: PaymentFacts,
    human_approved: bool,
) -> AuthzRequest:
    """Assemble the `pay_vendor` question."""
    return AuthzRequest(
        principal=f'Agent::"{run_id}"',
        action='Action::"pay_vendor"',
        resource=f'Vendor::"{vendor_id}"',
        context={
            "mandate": mandate.to_cedar_context(),
            "amountPaise": facts.amount_paise,
            "amount": arg_label(amount),
            "account": arg_label(account),
            "accountMatchesVendorMaster": facts.account_matches_vendor_master,
            "vendorMatchVerified": facts.vendor_match_verified,
            "isDuplicateInvoice": facts.is_duplicate_invoice,
            "humanApproved": human_approved,
        },
        entities=[
            {
                "uid": {"type": "Agent", "id": run_id},
                "attrs": {"onBehalfOf": {"__entity": {"type": "User", "id": user_id}}},
                "parents": [],
            },
            {
                "uid": {"type": "Vendor", "id": vendor_id},
                "attrs": {"status": vendor_status},
                "parents": [],
            },
            {"uid": {"type": "User", "id": user_id}, "attrs": {"role": "AP_LEAD"}, "parents": []},
        ],
    )


def build_email_request(
    run_id: str,
    user_id: str,
    mandate: Mandate,
    recipient: Labeled[Any],
    facts: EmailFacts,
    human_approved: bool,
) -> AuthzRequest:
    """Assemble the `send_email` question."""
    return AuthzRequest(
        principal=f'Agent::"{run_id}"',
        action='Action::"send_email"',
        resource='Mailbox::"outbound"',
        context={
            "mandate": mandate.to_cedar_context(),
            "recipient": arg_label(recipient),
            "recipientIsInternal": facts.recipient_is_internal,
            "recipientIsKnownContact": facts.recipient_is_known_contact,
            "bodyConfidentiality": facts.body_confidentiality,
            "attachmentSources": list(facts.attachment_sources),
            "humanApproved": human_approved,
        },
        entities=[
            {
                "uid": {"type": "Agent", "id": run_id},
                "attrs": {"onBehalfOf": {"__entity": {"type": "User", "id": user_id}}},
                "parents": [],
            },
            {"uid": {"type": "Mailbox", "id": "outbound"}, "attrs": {}, "parents": []},
            {"uid": {"type": "User", "id": user_id}, "attrs": {"role": "AP_LEAD"}, "parents": []},
        ],
    )
