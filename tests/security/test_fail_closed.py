"""Hardening: every way the enforcement point can break must end in a refusal.

The ordinary tests check that correct inputs produce correct decisions. These check the
opposite: that malformed, hostile and broken inputs never produce a payment. A guard whose
failure mode is "allow" is worse than no guard, because it is trusted.

Each case here is a way the system could plausibly fail in production — a store that
returns nothing, a policy file that has gone missing, a vendor record that disappeared
between lookup and payment — and each must refuse.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fixtures.hero import COMPANY, VENDORS
from hallmark.adapters.cedar_local.authorizer import CedarLocalAuthorizer
from hallmark.adapters.memory.stores import (
    FixedClock,
    InMemoryDecisionStore,
    InMemoryLedgerRepository,
    InMemoryLineageStore,
    InMemoryValueStore,
    InMemoryVendorRepository,
    SequentialIdGenerator,
)
from hallmark.application.pep import PolicyEnforcementPoint, RunContext
from hallmark.domain.labels import Confidentiality, Source, ValueType
from hallmark.domain.mandate import Mandate
from hallmark.domain.tools import ReasonCode, ToolOutcome
from hallmark.domain.values import Labeled
from hallmark.ports.authorizer import AuthzRequest, Decision

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"
MANDATE = Mandate(frozenset({"pay_vendor", "send_email"}), 50_000_000, 20_000_000)
RUN = RunContext("run-fc", "ananya", MANDATE)
SURYODAYA_ACCOUNT = "911020033456"


class Exploding:
    """A dependency that fails the way a real one does: at the worst moment."""

    def __init__(self, error: type[BaseException] = RuntimeError) -> None:
        self._error = error

    def __getattr__(self, name: str) -> Any:
        def boom(*_args: Any, **_kwargs: Any) -> Any:
            raise self._error(f"{name} failed")

        return boom


class AlwaysAllow:
    """A policy engine that says yes to everything.

    Used to prove the checks *before* the engine also hold: if resolution or the ground
    truth is wrong, an agreeable engine must not be able to rescue the payment.
    """

    def is_authorized(self, request: AuthzRequest) -> Decision:
        return Decision(allow=True, determining_policies=("stub-allow",))


def build(authorizer: Any = None, vendors: Any = None, ledger: Any = None, values: Any = None):
    store = values if values is not None else InMemoryValueStore()
    ledger_repo = ledger if ledger is not None else InMemoryLedgerRepository([])

    pep = PolicyEnforcementPoint(
        authorizer=authorizer or CedarLocalAuthorizer.from_directory(POLICY_DIR),
        values=store,
        lineage=InMemoryLineageStore(),
        decisions=InMemoryDecisionStore(),
        vendors=vendors if vendors is not None else InMemoryVendorRepository(VENDORS),
        ledger=ledger_repo,
        company=COMPANY,
        ids=SequentialIdGenerator(),
        clock=FixedClock(),
    )
    return pep, store, ledger_repo


def put(store: InMemoryValueStore, handle: str, value: Any, vtype: ValueType, sources: set) -> None:
    store.put(
        Labeled(
            handle=handle,
            value=value,
            vtype=vtype,
            sources=frozenset(sources),
            confidentiality=Confidentiality.INTERNAL,
            run_id="run-fc",
        )
    )


def seed_valid(store: InMemoryValueStore, account: str = SURYODAYA_ACCOUNT) -> None:
    put(store, "h_v", "v-suryodaya", ValueType.ENUM, {Source.COMPANY_DB})
    put(store, "h_acc", account, ValueType.ACCOUNT_NUMBER, {Source.COMPANY_DB})
    put(store, "h_amt", 10_000_000, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})
    put(store, "h_inv", "INV-FC-1", ValueType.INVOICE_NUMBER, {Source.EXTERNAL_EMAIL})


def test_a_broken_policy_engine_refuses_rather_than_allows() -> None:
    pep, store, ledger = build(authorizer=Exploding())
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ENFORCEMENT_ERROR
    assert ledger.entries() == []


def test_a_broken_vendor_repository_refuses() -> None:
    """The vendor master is where the only payable account lives."""
    pep, store, ledger = build(vendors=Exploding())
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert ledger.entries() == []


def test_a_broken_ledger_refuses_rather_than_skipping_duplicate_detection() -> None:
    """If duplicate detection cannot run, the payment must not proceed without it."""
    pep, store, _ = build(ledger=Exploding())
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ENFORCEMENT_ERROR


def test_a_vendor_that_vanished_between_lookup_and_payment_refuses() -> None:
    """Records change. A handle to a vendor that no longer exists is not payable."""
    pep, store, ledger = build(vendors=InMemoryVendorRepository([]))
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert ledger.entries() == []


@pytest.mark.parametrize(
    "amount",
    ["not a number", None, {"nested": "object"}, [1, 2, 3], float("nan")],
)
def test_a_malformed_amount_refuses(amount: Any) -> None:
    """An amount that cannot be compared to a limit cannot be under it."""
    pep, store, ledger = build()
    seed_valid(store)
    put(store, "h_bad", amount, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_bad", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert ledger.entries() == []


def test_an_agreeable_policy_engine_cannot_rescue_a_broken_lookup() -> None:
    """Defence in depth: the checks before the engine must hold on their own."""
    pep, store, ledger = build(authorizer=AlwaysAllow(), vendors=Exploding())
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert ledger.entries() == []


def test_an_agreeable_policy_engine_still_cannot_use_an_unknown_handle() -> None:
    pep, store, ledger = build(authorizer=AlwaysAllow())
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_missing", "h_amt", "h_inv", True)

    assert result.reason_code is ReasonCode.UNKNOWN_HANDLE
    assert ledger.entries() == []


def test_a_store_that_returns_nothing_refuses() -> None:
    """An empty store must not read as "no restrictions"."""

    class EmptyStore:
        def put(self, value: Any) -> None: ...
        def get(self, run_id: str, handle: str) -> None:
            return None

    pep, _, ledger = build(values=EmptyStore())

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.UNKNOWN_HANDLE
    assert ledger.entries() == []


def test_a_missing_policy_directory_refuses_at_construction() -> None:
    """Better to fail at startup than to run with no rules."""
    with pytest.raises(FileNotFoundError):
        CedarLocalAuthorizer.from_directory(Path("does/not/exist"))


def test_an_empty_policy_set_cannot_permit_anything() -> None:
    """With no policies, deny-by-default must mean deny."""
    authorizer = CedarLocalAuthorizer("")
    pep, store, ledger = build(authorizer=authorizer)
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert ledger.entries() == []


def test_a_value_with_no_recorded_provenance_is_not_payable() -> None:
    """Unknown provenance reads as untrusted, because a bug must not grant trust."""
    pep, store, ledger = build()
    seed_valid(store)
    store.put(
        Labeled(
            handle="h_nosource",
            value=SURYODAYA_ACCOUNT,
            vtype=ValueType.ACCOUNT_NUMBER,
            sources=frozenset(),
            confidentiality=Confidentiality.INTERNAL,
            run_id="run-fc",
        )
    )

    result = pep.pay_vendor(RUN, "h_v", "h_nosource", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ACCOUNT_NOT_FROM_VENDOR_MASTER
    assert ledger.entries() == []


def test_a_broken_event_publisher_does_not_block_a_decision() -> None:
    """The inverse case: telemetry failing must not stop enforcement working.

    Failing closed applies to the decision path. A console that cannot be told is a
    degraded console, not a reason to refuse legitimate work.
    """
    pep, store, ledger = build()
    pep._events = Exploding()  # noqa: SLF001 - exercising the failure path deliberately
    seed_valid(store)

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_amt", "h_inv", True)

    assert result.status is ToolOutcome.EXECUTED
    assert len(ledger.entries()) == 1
