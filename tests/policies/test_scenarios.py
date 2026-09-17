"""Table-driven policy scenarios.

Each case states a situation and the answer the policy set must give. These are the
executable form of the guarantees: if one of these flips, a guarantee has been lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from hallmark.adapters.cedar_local.authorizer import CedarLocalAuthorizer
from hallmark.ports.authorizer import AuthzRequest

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"

TRUSTED = {"sources": ["COMPANY_DB"], "trusted": True}
FROM_EMAIL = {"sources": ["EXTERNAL_EMAIL", "MODEL_READER"], "trusted": False}
FROM_ATTACHMENT = {"sources": ["EXTERNAL_ATTACHMENT", "MODEL_READER"], "trusted": False}

MANDATE = {
    "allowedActions": ["pay_vendor", "send_email"],
    "maxAmountPaise": 50_000_000,
    "autoApproveLimitPaise": 20_000_000,
}
MANDATE_NO_PAY = {**MANDATE, "allowedActions": ["send_email"]}
MANDATE_NO_EMAIL = {**MANDATE, "allowedActions": ["pay_vendor"]}


@pytest.fixture(scope="module")
def authorizer() -> CedarLocalAuthorizer:
    return CedarLocalAuthorizer.from_directory(POLICY_DIR)


def pay_request(
    *,
    amount: int = 10_000_000,
    account: dict = TRUSTED,
    amount_label: dict = FROM_EMAIL,
    matches_master: bool = True,
    vendor_verified: bool = True,
    duplicate: bool = False,
    human_approved: bool = False,
    vendor_status: str = "ACTIVE",
    mandate: dict | None = None,
) -> AuthzRequest:
    return AuthzRequest(
        principal='Agent::"run-1"',
        action='Action::"pay_vendor"',
        resource='Vendor::"v-suryodaya"',
        context={
            "mandate": mandate or MANDATE,
            "amountPaise": amount,
            "amount": amount_label,
            "account": account,
            "accountMatchesVendorMaster": matches_master,
            "vendorMatchVerified": vendor_verified,
            "isDuplicateInvoice": duplicate,
            "humanApproved": human_approved,
        },
        entities=[
            {
                "uid": {"type": "Vendor", "id": "v-suryodaya"},
                "attrs": {"status": vendor_status},
                "parents": [],
            }
        ],
    )


def email_request(
    *,
    recipient: dict = TRUSTED,
    internal: bool = False,
    known_contact: bool = True,
    confidentiality: str = "PUBLIC",
    human_approved: bool = False,
    mandate: dict | None = None,
) -> AuthzRequest:
    return AuthzRequest(
        principal='Agent::"run-1"',
        action='Action::"send_email"',
        resource='Mailbox::"outbound"',
        context={
            "mandate": mandate or MANDATE,
            "recipient": recipient,
            "recipientIsInternal": internal,
            "recipientIsKnownContact": known_contact,
            "bodyConfidentiality": confidentiality,
            "attachmentSources": [],
            "humanApproved": human_approved,
        },
        entities=[{"uid": {"type": "Mailbox", "id": "outbound"}, "attrs": {}, "parents": []}],
    )


@dataclass
class Case:
    name: str
    request: AuthzRequest
    allow: bool
    expect_policy: str | None = None


PAYMENT_CASES = [
    Case("legit invoice under the auto limit is paid", pay_request(amount=10_000_000), True),
    Case("exactly at the auto limit is still automatic", pay_request(amount=20_000_000), True),
    Case(
        "exactly at the mandate cap needs a human",
        pay_request(amount=50_000_000),
        False,
        "pay-above-auto-limit-needs-human",
    ),
    Case(
        "above the auto limit needs a human",
        pay_request(amount=38_000_000),
        False,
        "pay-above-auto-limit-needs-human",
    ),
    Case(
        "above the auto limit is paid once approved",
        pay_request(amount=38_000_000, human_approved=True),
        True,
    ),
    Case("above the mandate cap is refused", pay_request(amount=60_000_000), False),
    Case(
        "above the mandate cap stays refused even with approval",
        pay_request(amount=60_000_000, human_approved=True),
        False,
    ),
    Case(
        "account from an email is refused",
        pay_request(account=FROM_EMAIL, matches_master=False),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "account from an email stays refused with human approval",
        pay_request(account=FROM_EMAIL, matches_master=False, human_approved=True),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "account from an attachment stays refused with human approval",
        pay_request(account=FROM_ATTACHMENT, matches_master=False, human_approved=True),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "untrusted account is refused even when the digits happen to match",
        pay_request(account=FROM_EMAIL, matches_master=False),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "trusted account that is not the one on file is refused",
        pay_request(account=TRUSTED, matches_master=False),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "unverified vendor needs a human",
        pay_request(vendor_verified=False),
        False,
        "pay-vendor-match-required",
    ),
    Case(
        "unverified vendor is paid once approved",
        pay_request(vendor_verified=False, human_approved=True),
        True,
    ),
    Case("duplicate invoice is refused", pay_request(duplicate=True), False, "pay-no-duplicates"),
    Case(
        "duplicate invoice stays refused with human approval",
        pay_request(duplicate=True, human_approved=True),
        False,
        "pay-no-duplicates",
    ),
    Case("blocked vendor is refused", pay_request(vendor_status="BLOCKED"), False),
    Case(
        "blocked vendor stays refused with human approval",
        pay_request(vendor_status="BLOCKED", human_approved=True),
        False,
    ),
    Case(
        "mandate without pay_vendor refuses payment",
        pay_request(mandate=MANDATE_NO_PAY),
        False,
    ),
    Case(
        "mandate without pay_vendor stays refused with approval",
        pay_request(mandate=MANDATE_NO_PAY, human_approved=True),
        False,
    ),
    Case(
        "untrusted amount is fine when it is within the caps",
        pay_request(amount_label=FROM_EMAIL, amount=10_000_000),
        True,
    ),
    Case(
        "the exact BEC case is refused",
        pay_request(
            amount=46_200_000,
            account=FROM_EMAIL,
            matches_master=False,
            vendor_verified=False,
        ),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "the exact BEC case is refused even if a tired approver says yes",
        pay_request(
            amount=46_200_000,
            account=FROM_EMAIL,
            matches_master=False,
            vendor_verified=False,
            human_approved=True,
        ),
        False,
        "pay-account-must-be-master",
    ),
    Case(
        "several problems at once are still refused",
        pay_request(
            account=FROM_EMAIL,
            matches_master=False,
            duplicate=True,
            vendor_verified=False,
            vendor_status="BLOCKED",
        ),
        False,
    ),
]

EMAIL_CASES = [
    Case("public template to a known contact is sent", email_request(), True),
    Case("public template to an internal address is sent", email_request(internal=True), True),
    Case(
        "confidential data to an internal address is sent",
        email_request(confidentiality="CONFIDENTIAL", internal=True),
        True,
    ),
    Case(
        "confidential data to a known external contact is refused",
        email_request(confidentiality="CONFIDENTIAL", known_contact=True),
        False,
        "email-confidential-internal-only",
    ),
    Case(
        "confidential data to an external address stays refused with approval",
        email_request(confidentiality="CONFIDENTIAL", known_contact=True, human_approved=True),
        False,
        "email-confidential-internal-only",
    ),
    Case(
        "recipient from an attachment who is not a known contact is refused",
        email_request(recipient=FROM_ATTACHMENT, known_contact=False),
        False,
        "email-recipient-must-be-trusted",
    ),
    Case(
        "the exfiltration case is refused",
        email_request(
            recipient=FROM_ATTACHMENT,
            known_contact=False,
            confidentiality="CONFIDENTIAL",
        ),
        False,
    ),
    Case(
        "recipient from an email who is a known contact is allowed",
        email_request(recipient=FROM_EMAIL, known_contact=True),
        True,
    ),
    Case(
        "mandate without send_email refuses sending",
        email_request(mandate=MANDATE_NO_EMAIL),
        False,
    ),
]

ALL_CASES = PAYMENT_CASES + EMAIL_CASES


def test_at_least_thirty_scenarios() -> None:
    assert len(ALL_CASES) >= 30, f"only {len(ALL_CASES)} scenarios"


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.name)
def test_policy_scenario(authorizer: CedarLocalAuthorizer, case: Case) -> None:
    decision = authorizer.is_authorized(case.request)
    assert decision.allow is case.allow, (
        f"{case.name}: expected allow={case.allow}, got {decision.allow} "
        f"(policies={decision.determining_policies}, errors={decision.errors})"
    )
    if case.expect_policy:
        assert case.expect_policy in decision.determining_policies, (
            f"{case.name}: expected {case.expect_policy} to decide, "
            f"got {decision.determining_policies}"
        )


def test_no_policy_permits_changing_bank_details(authorizer: CedarLocalAuthorizer) -> None:
    """There is no action for it, so deny-by-default must refuse it outright."""
    decision = authorizer.is_authorized(
        AuthzRequest(
            principal='Agent::"run-1"',
            action='Action::"update_vendor_bank_details"',
            resource='Vendor::"v-suryodaya"',
            context={},
        )
    )
    assert decision.allow is False
