"""A planner that loses the thread must stall, not run forever."""

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
from hallmark.application.agent_tools import AgentTools
from hallmark.application.pep import PolicyEnforcementPoint, RunContext
from hallmark.application.scripted_run import RegexInvoiceReader
from hallmark.domain.mandate import Mandate

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"
MANDATE = Mandate(frozenset({"pay_vendor", "send_email"}), 50_000_000, 20_000_000)


@pytest.fixture
def tools() -> AgentTools:
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
    return AgentTools(
        run=RunContext("run-b", "ananya", MANDATE),
        pep=pep,
        inbox=InMemoryInboxRepository(build_inbox()),
        vendors=vendors,
        values=values,
        lineage=lineage,
        ids=ids,
        clock=clock,
        reader=RegexInvoiceReader(),
    )


def test_tools_stop_answering_once_the_budget_is_spent(tools: AgentTools) -> None:
    listing = tools.list_inbox()
    handle = listing["emails"][0]["email_handle"]
    tools.start_episode(budget=3)

    assert "error" not in tools.read_email(handle)
    assert "error" not in tools.read_email(handle)
    assert "error" not in tools.read_email(handle)
    assert tools.read_email(handle)["error"] == "CALL_BUDGET_EXHAUSTED"


def test_an_exhausted_budget_denies_payment_rather_than_letting_it_through(
    tools: AgentTools,
) -> None:
    """Running out of budget must fail closed, like every other refusal."""
    tools.start_episode(budget=1)
    tools.read_email("anything")

    result = tools.pay_vendor("h_1", "h_2", "h_3", "h_4")
    assert result["status"] == "DENIED"
    assert result["reason_code"] == "CALL_BUDGET_EXHAUSTED"


def test_each_episode_starts_with_a_fresh_budget(tools: AgentTools) -> None:
    listing = tools.list_inbox()
    handle = listing["emails"][0]["email_handle"]

    tools.start_episode(budget=1)
    tools.read_email(handle)
    assert tools.read_email(handle)["error"] == "CALL_BUDGET_EXHAUSTED"

    tools.start_episode(budget=1)
    assert "error" not in tools.read_email(handle)


def test_without_an_episode_the_budget_is_unlimited(tools: AgentTools) -> None:
    """The scripted planner drives the same tools and is bounded by its own loop."""
    listing = tools.list_inbox()
    handle = listing["emails"][0]["email_handle"]

    for _ in range(25):
        assert "error" not in tools.read_email(handle)
