"""The comparison the whole project rests on.

Same inbox, same systems, same procedure. The only difference is whether the enforcement
point sits between the agent and the ledger. If the unprotected run did not actually lose
the money, there would be nothing to demonstrate — so this asserts that it does, and that
the protected run does not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.hero import (
    BEC_ATTACKER_ACCOUNT,
    COMPANY,
    VENDORS,
    build_inbox,
)
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
from hallmark.baseline.scripted import BaselineRun, ScriptedBaseline
from hallmark.domain.mandate import Mandate

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"
MANDATE = Mandate(frozenset({"pay_vendor", "send_email"}), 50_000_000, 20_000_000)
SURYODAYA_REAL_ACCOUNT = "911020033456"


@pytest.fixture
def unprotected() -> BaselineRun:
    vendors = InMemoryVendorRepository(VENDORS)
    return ScriptedBaseline(InMemoryInboxRepository(build_inbox()), vendors).run()


@pytest.fixture
def protected() -> RunSummary:
    values = InMemoryValueStore()
    lineage = InMemoryLineageStore()
    ids = SequentialIdGenerator()
    clock = FixedClock()
    vendors = InMemoryVendorRepository(VENDORS)

    pep = PolicyEnforcementPoint(
        authorizer=CedarLocalAuthorizer.from_directory(POLICY_DIR),
        values=values,
        lineage=lineage,
        decisions=InMemoryDecisionStore(),
        vendors=vendors,
        ledger=InMemoryLedgerRepository([]),
        company=COMPANY,
        ids=ids,
        clock=clock,
    )
    runner = ScriptedRun(
        pep, InMemoryInboxRepository(build_inbox()), vendors, values, lineage, ids, clock
    )
    return runner.run(RunContext("run-compare", "ananya", MANDATE))


def test_the_unprotected_agent_pays_the_attacker(unprotected: BaselineRun) -> None:
    """Without enforcement, following the document loses the money.

    This is the failure the project exists to prevent. If it ever stops happening, the
    comparison is measuring something else and the fixture needs re-examining.
    """
    to_attacker = unprotected.paid_to(BEC_ATTACKER_ACCOUNT)

    assert len(to_attacker) == 1, "the unprotected run must fall for the bank-change email"
    assert to_attacker[0].amount_paise == 46_200_000
    assert to_attacker[0].vendor_id == "v-suryodaya"


def test_the_protected_run_refuses_the_same_payment(protected: RunSummary) -> None:
    attack = protected.by_id("email-19")

    assert attack.status == "DENIED"
    assert attack.reason_code == "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    assert "pay-account-must-be-master" in attack.determining_policies


def test_the_unprotected_agent_is_not_simply_broken(unprotected: BaselineRun) -> None:
    """A baseline that fails at everything would prove nothing.

    It pays the legitimate invoices correctly. It is competent and obedient, and obedience
    is all the attack needs.
    """
    legitimate = [p for p in unprotected.payments if p.account_number != BEC_ATTACKER_ACCOUNT]

    assert len(legitimate) >= 16
    assert all(p.amount_paise > 0 for p in legitimate)


def test_the_unprotected_agent_pays_real_vendors_correctly(unprotected: BaselineRun) -> None:
    """Its ordinary payments go to the right accounts, which is why it looks fine."""
    suryodaya = [
        p
        for p in unprotected.payments
        if p.vendor_id == "v-suryodaya" and p.invoice_number != "INV-SM-2291"
    ]
    assert suryodaya, "the legitimate Suryodaya invoices should still be paid"
    assert all(p.account_number == SURYODAYA_REAL_ACCOUNT for p in suryodaya)


def test_both_runs_do_the_same_routine_work(
    unprotected: BaselineRun, protected: RunSummary
) -> None:
    """Enforcement costs nothing on the sixteen invoices that are fine."""
    assert protected.count("EXECUTED") == 16

    routine = [
        p
        for p in unprotected.payments
        if p.account_number != BEC_ATTACKER_ACCOUNT and p.amount_paise <= 20_000_000
    ]
    assert len(routine) == 16


def test_the_unprotected_agent_pays_a_large_invoice_without_asking(
    unprotected: BaselineRun, protected: RunSummary
) -> None:
    """A second difference, and a quieter one than the stolen payment.

    The ₹3,80,000 invoice is genuine, so nothing about it looks wrong. The unprotected
    agent simply pays it, because it has no notion of an amount that warrants a person.
    The protected run pays the same invoice only after somebody approves it.
    """
    large = [p for p in unprotected.payments if p.amount_paise == 38_000_000]

    assert len(large) == 1, "the unprotected run pays it outright"
    assert large[0].vendor_id == "v-arcfield"

    assert protected.by_id("email-17").status == "PENDING_APPROVAL"
    assert protected.by_id("email-17").reason_code == "ABOVE_AUTO_APPROVE_LIMIT"


def test_the_difference_between_the_runs_is_one_payment(
    unprotected: BaselineRun, protected: RunSummary
) -> None:
    """The headline number: what the attack costs when nothing is watching."""
    lost = sum(p.amount_paise for p in unprotected.paid_to(BEC_ATTACKER_ACCOUNT))

    assert lost == 46_200_000
    assert protected.by_id("email-19").status == "DENIED"


def test_the_protected_run_still_flags_the_attack_for_a_person(protected: RunSummary) -> None:
    """Refusing is not enough on its own; somebody has to look at it."""
    assert "email-19" in protected.reviews_opened
