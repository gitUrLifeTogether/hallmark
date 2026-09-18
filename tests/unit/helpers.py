"""Shared test harness: a full tool surface over in-memory adapters.

Several suites need the same wiring. Building it once means a change to the constructor
does not have to be made in five places, and the tests stay about behaviour.
"""

from __future__ import annotations

from pathlib import Path

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
from hallmark.application.agent_tools import AgentTools
from hallmark.application.pep import PolicyEnforcementPoint, RunContext
from hallmark.application.scripted_run import RegexInvoiceReader
from hallmark.domain.mandate import Mandate

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"
MANDATE = Mandate(frozenset({"pay_vendor", "send_email"}), 50_000_000, 20_000_000)


def build_tools_for_test(run_id: str = "run-test") -> AgentTools:
    values = InMemoryValueStore()
    lineage = InMemoryLineageStore()
    ids = SequentialIdGenerator()
    clock = FixedClock()
    vendors = InMemoryVendorRepository(list(VENDORS))

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
    return AgentTools(
        run=RunContext(run_id, "ananya", MANDATE),
        pep=pep,
        inbox=InMemoryInboxRepository(build_inbox()),
        vendors=vendors,
        values=values,
        lineage=lineage,
        ids=ids,
        clock=clock,
        reader=RegexInvoiceReader(),
    )
