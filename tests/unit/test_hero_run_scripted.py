"""M1 acceptance: the scripted run over the hero inbox.

No model is involved, so the outcome is fully determined by labels, facts and policy.
That is the point: these results are properties of the design rather than of how a
language model happened to behave on the day.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.hero import COMPANY, VENDORS, build_inbox
from hallmark.adapters.cedar_local.authorizer import CedarLocalAuthorizer
from hallmark.adapters.memory.stores import (
    FixedClock,
    InMemoryDecisionStore,
    InMemoryInboxRepository,
    InMemoryLedgerRepository,
    InMemoryLineageStore,
    InMemoryValueStore,
    InMemoryVendorRepository,
    SequentialIdGenerator,
)
from hallmark.application.pep import PolicyEnforcementPoint, RunContext
from hallmark.application.scripted_run import RunSummary, ScriptedRun
from hallmark.domain.mandate import Mandate

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"

#: Pay anything under Rs 5,00,000; anything over Rs 2,00,000 needs a person.
MANDATE = Mandate(
    allowed_actions=frozenset({"pay_vendor", "send_email"}),
    max_amount_paise=50_000_000,
    auto_approve_limit_paise=20_000_000,
)


@pytest.fixture
def summary() -> RunSummary:
    values = InMemoryValueStore()
    lineage = InMemoryLineageStore()
    ids = SequentialIdGenerator()
    clock = FixedClock()
    vendors = InMemoryVendorRepository(VENDORS)

    # The ledger starts empty. Email 18 becomes a duplicate because email 01 was paid
    # earlier in this same run, which is how a resend actually gets caught.
    ledger = InMemoryLedgerRepository([])

    pep = PolicyEnforcementPoint(
        authorizer=CedarLocalAuthorizer.from_directory(POLICY_DIR),
        values=values,
        lineage=lineage,
        decisions=InMemoryDecisionStore(),
        vendors=vendors,
        ledger=ledger,
        company=COMPANY,
        ids=ids,
        clock=clock,
    )

    runner = ScriptedRun(
        pep=pep,
        inbox=InMemoryInboxRepository(build_inbox()),
        vendors=vendors,
        values=values,
        lineage=lineage,
        ids=ids,
        clock=clock,
    )
    return runner.run(RunContext(run_id="run-1", user_id="ananya", mandate=MANDATE))


def test_the_bank_change_attack_is_refused(summary: RunSummary) -> None:
    """The heart of it: money never reaches an account that came from an email."""
    attack = summary.by_id("email-19")
    assert attack.status == "DENIED"
    assert attack.reason_code == "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    assert "pay-account-must-be-master" in attack.determining_policies


def test_the_attack_opens_a_review_for_a_human(summary: RunSummary) -> None:
    assert "email-19" in summary.reviews_opened
    assert summary.by_id("email-19").flag_reason == "SUSPICIOUS_BANK_CHANGE"


def test_the_duplicate_invoice_is_refused(summary: RunSummary) -> None:
    duplicate = summary.by_id("email-18")
    assert duplicate.status == "DENIED"
    assert duplicate.reason_code == "DUPLICATE_INVOICE"


def test_the_large_invoice_waits_for_a_person(summary: RunSummary) -> None:
    large = summary.by_id("email-17")
    assert large.status == "PENDING_APPROVAL"
    assert large.reason_code == "ABOVE_AUTO_APPROVE_LIMIT"


def test_the_sixteen_routine_invoices_are_paid(summary: RunSummary) -> None:
    """The system still does its job; blocking everything would be no achievement."""
    assert summary.count("EXECUTED") == 16


def test_the_exfiltration_attempt_is_refused(summary: RunSummary) -> None:
    """Confidential company data cannot leave for an address found in an attachment."""
    exfil = summary.by_id("email-20")
    assert exfil.status == "DENIED"
    assert exfil.reason_code == "CONFIDENTIAL_TO_EXTERNAL"
    assert "email-confidential-internal-only" in exfil.determining_policies


def test_the_run_has_the_expected_shape(summary: RunSummary) -> None:
    # 16 paid, 1 waiting on a person, and 3 refused: the duplicate, the bank-change
    # attack and the exfiltration attempt.
    assert summary.count("EXECUTED") == 16
    assert summary.count("PENDING_APPROVAL") == 1
    assert summary.count("DENIED") == 3
    assert len(summary.outcomes) == 20


def test_the_result_is_the_same_every_time() -> None:
    """Determinism is what lets this stand as an acceptance gate."""

    def run_once() -> list[tuple[str, str]]:
        values = InMemoryValueStore()
        lineage = InMemoryLineageStore()
        ids = SequentialIdGenerator()
        clock = FixedClock()
        vendors = InMemoryVendorRepository(VENDORS)
        ledger = InMemoryLedgerRepository([])
        pep = PolicyEnforcementPoint(
            authorizer=CedarLocalAuthorizer.from_directory(POLICY_DIR),
            values=values,
            lineage=lineage,
            decisions=InMemoryDecisionStore(),
            vendors=vendors,
            ledger=ledger,
            company=COMPANY,
            ids=ids,
            clock=clock,
        )
        runner = ScriptedRun(
            pep, InMemoryInboxRepository(build_inbox()), vendors, values, lineage, ids, clock
        )
        result = runner.run(RunContext("run-1", "ananya", MANDATE))
        return [(o.email_id, o.status) for o in result.outcomes]

    assert run_once() == run_once()
