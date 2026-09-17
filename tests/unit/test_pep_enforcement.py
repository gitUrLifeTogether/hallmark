"""Enforcement behaviour that is not about any particular policy."""

from __future__ import annotations

from pathlib import Path

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
RUN = RunContext("run-1", "ananya", MANDATE)


class ExplodingAuthorizer:
    """Stands in for a policy engine having a bad day."""

    def is_authorized(self, request: AuthzRequest) -> Decision:
        raise RuntimeError("policy engine unreachable")


def build(authorizer: object | None = None) -> tuple[PolicyEnforcementPoint, InMemoryValueStore]:
    values = InMemoryValueStore()
    ids = SequentialIdGenerator()
    pep = PolicyEnforcementPoint(
        authorizer=authorizer or CedarLocalAuthorizer.from_directory(POLICY_DIR),  # type: ignore[arg-type]
        values=values,
        lineage=InMemoryLineageStore(),
        decisions=InMemoryDecisionStore(),
        vendors=InMemoryVendorRepository(VENDORS),
        ledger=InMemoryLedgerRepository([]),
        company=COMPANY,
        ids=ids,
        clock=FixedClock(),
    )
    return pep, values


def put(
    values: InMemoryValueStore, handle: str, value: object, vtype: ValueType, sources: set[Source]
) -> str:
    values.put(
        Labeled(
            handle=handle,
            value=value,
            vtype=vtype,
            sources=frozenset(sources),
            confidentiality=Confidentiality.INTERNAL,
            run_id="run-1",
        )
    )
    return handle


@pytest.mark.parametrize("bad_handle", ["912020033456", "", "not-a-handle", None, 42])
def test_a_literal_where_a_handle_belongs_is_refused(bad_handle: object) -> None:
    """The planner cannot smuggle a raw account number past the handle requirement."""
    pep, values = build()
    put(values, "h_v", "v-suryodaya", ValueType.ENUM, {Source.COMPANY_DB})
    put(values, "h_a", 10_000_000, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})
    put(values, "h_i", "INV-SM-1", ValueType.INVOICE_NUMBER, {Source.EXTERNAL_EMAIL})

    result = pep.pay_vendor(RUN, "h_v", bad_handle, "h_a", "h_i", True)  # type: ignore[arg-type]
    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ARG_MUST_BE_HANDLE


def test_an_unknown_handle_is_refused() -> None:
    pep, values = build()
    put(values, "h_v", "v-suryodaya", ValueType.ENUM, {Source.COMPANY_DB})
    put(values, "h_a", 10_000_000, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})
    put(values, "h_i", "INV-SM-1", ValueType.INVOICE_NUMBER, {Source.EXTERNAL_EMAIL})

    result = pep.pay_vendor(RUN, "h_v", "h_missing", "h_a", "h_i", True)
    assert result.reason_code is ReasonCode.UNKNOWN_HANDLE


def test_enforcement_failure_denies_rather_than_pays() -> None:
    """If the guard itself breaks, nothing moves."""
    pep, values = build(ExplodingAuthorizer())
    put(values, "h_v", "v-suryodaya", ValueType.ENUM, {Source.COMPANY_DB})
    put(values, "h_acc", "911020033456", ValueType.ACCOUNT_NUMBER, {Source.COMPANY_DB})
    put(values, "h_a", 10_000_000, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})
    put(values, "h_i", "INV-SM-1", ValueType.INVOICE_NUMBER, {Source.EXTERNAL_EMAIL})

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_a", "h_i", True)
    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ENFORCEMENT_ERROR


def test_matching_digits_from_an_email_are_still_not_the_account_on_file() -> None:
    """An attacker echoing the real account back gains nothing.

    The digits match the vendor master, but the value came from an email, so the fact
    check refuses to call it a match and the payment is refused.
    """
    pep, values = build()
    put(values, "h_v", "v-suryodaya", ValueType.ENUM, {Source.COMPANY_DB})
    put(
        values,
        "h_acc",
        "911020033456",
        ValueType.ACCOUNT_NUMBER,
        {Source.EXTERNAL_EMAIL, Source.MODEL_READER},
    )
    put(values, "h_a", 10_000_000, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})
    put(values, "h_i", "INV-SM-9", ValueType.INVOICE_NUMBER, {Source.EXTERNAL_EMAIL})

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_a", "h_i", True)
    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ACCOUNT_NOT_FROM_VENDOR_MASTER


def test_a_payment_to_the_account_on_file_goes_through() -> None:
    pep, values = build()
    put(values, "h_v", "v-suryodaya", ValueType.ENUM, {Source.COMPANY_DB})
    put(values, "h_acc", "911020033456", ValueType.ACCOUNT_NUMBER, {Source.COMPANY_DB})
    put(values, "h_a", 10_000_000, ValueType.MONEY_PAISE, {Source.EXTERNAL_EMAIL})
    put(values, "h_i", "INV-SM-7", ValueType.INVOICE_NUMBER, {Source.EXTERNAL_EMAIL})

    result = pep.pay_vendor(RUN, "h_v", "h_acc", "h_a", "h_i", True)
    assert result.status is ToolOutcome.EXECUTED
    assert result.txn_id is not None
