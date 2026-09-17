"""The tool surface: what it hands the planner, and what it refuses to."""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.hero import BEC_ATTACKER_ACCOUNT, COMPANY, VENDORS, build_inbox
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
from hallmark.domain.labels import Source
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
        run=RunContext("run-t", "ananya", MANDATE),
        pep=pep,
        inbox=InMemoryInboxRepository(build_inbox()),
        vendors=vendors,
        values=values,
        lineage=lineage,
        ids=ids,
        clock=clock,
        reader=RegexInvoiceReader(),
    )


def open_email(tools: AgentTools, email_id: str) -> dict:
    inbox = tools.list_inbox()
    handle = next(
        e["email_handle"]
        for e in inbox["emails"]
        if tools._email_by_handle[e["email_handle"]] == email_id
    )
    return tools.read_email(handle)


def test_the_inbox_listing_carries_no_subjects_or_senders(tools: AgentTools) -> None:
    listing = tools.list_inbox()
    for entry in listing["emails"]:
        assert set(entry) == {"email_handle", "received_at", "has_attachments"}


def test_reading_an_email_returns_handles_not_text(tools: AgentTools) -> None:
    opened = open_email(tools, "email-01")
    assert opened["body_handle"].startswith("h_")
    assert opened["sender_domain_handle"].startswith("h_")
    assert "body" not in opened
    assert "subject" not in opened


def test_amounts_are_shown_but_accounts_are_masked(tools: AgentTools) -> None:
    """The planner can reason about money without reading prose or full accounts."""
    opened = open_email(tools, "email-01")
    extracted = tools.extract_invoice(opened["body_handle"])
    fields = extracted["fields"]

    assert fields["amount"]["display"] == "₹42,500.00"
    assert fields["bank_account"]["display"].startswith("XXXX")
    assert VENDORS[0].account_number not in fields["bank_account"]["display"]


def test_the_attackers_account_is_never_shown_in_full(tools: AgentTools) -> None:
    opened = open_email(tools, "email-19")
    extracted = tools.extract_invoice(opened["body_handle"])
    account = extracted["fields"]["bank_account"]

    assert BEC_ATTACKER_ACCOUNT not in account.get("display", "")
    assert account["display"].endswith("1234")


def test_a_failed_dkim_is_reported_as_an_enum(tools: AgentTools) -> None:
    assert open_email(tools, "email-19")["auth"]["dkim"] == "fail"
    assert open_email(tools, "email-01")["auth"]["dkim"] == "pass"


def test_lookup_reports_whether_the_sender_domain_really_matches(tools: AgentTools) -> None:
    """The lookalike domain in the attack must not read as a match."""
    opened = open_email(tools, "email-19")
    fields = tools.extract_invoice(opened["body_handle"])["fields"]
    vendor = tools.lookup_vendor(fields["gstin"]["handle"], opened["sender_domain_handle"])

    assert vendor["found"] is True
    assert vendor["vendor_id"] == "v-suryodaya"
    assert vendor["domain_matches"] is False


def test_an_unknown_handle_returns_an_enum_not_an_exception(tools: AgentTools) -> None:
    assert tools.read_email("h_nope") == {"error": "UNKNOWN_HANDLE"}
    assert tools.extract_invoice("h_nope") == {"error": "UNKNOWN_HANDLE"}


def test_paying_the_attackers_account_is_refused_through_the_tool(tools: AgentTools) -> None:
    """The full path a fooled planner would take, ending in a refusal."""
    opened = open_email(tools, "email-19")
    fields = tools.extract_invoice(opened["body_handle"])["fields"]
    vendor = tools.lookup_vendor(fields["gstin"]["handle"], opened["sender_domain_handle"])

    result = tools.pay_vendor(
        vendor_handle=vendor["vendor_handle"],
        account_handle=fields["bank_account"]["handle"],
        amount_handle=fields["amount"]["handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=False,
    )

    assert "DENIED" in result["status"]
    assert result["reason_code"] == "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    assert "pay-account-must-be-master" in result["determining_policies"]
    assert "open_bank_change_review" in result["suggested_next"]


def test_paying_the_account_on_file_succeeds(tools: AgentTools) -> None:
    opened = open_email(tools, "email-01")
    fields = tools.extract_invoice(opened["body_handle"])["fields"]
    vendor = tools.lookup_vendor(fields["gstin"]["handle"], opened["sender_domain_handle"])

    result = tools.pay_vendor(
        vendor_handle=vendor["vendor_handle"],
        account_handle=vendor["account_on_file_handle"],
        amount_handle=fields["amount"]["handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=True,
    )
    assert "EXECUTED" in result["status"]


def test_emailing_the_vendor_master_outside_is_refused(tools: AgentTools) -> None:
    opened = open_email(tools, "email-20")
    export = tools.export_vendor_master()
    # The recipient address came out of the attachment, so it is untrusted by construction.
    recipient = tools._ingest(
        "compliance-check@vendor-onboarding-portal.example",
        {Source.EXTERNAL_ATTACHMENT},
    )

    result = tools.send_email(
        recipient_handle=recipient.handle,
        template_id="NEED_INFO",
        attachment_handles=[export["export_handle"]],
    )
    assert "DENIED" in result["status"]
    assert result["reason_code"] == "CONFIDENTIAL_TO_EXTERNAL"
    assert opened["body_handle"].startswith("h_")


def test_an_unrecognised_flag_reason_falls_back_rather_than_failing(tools: AgentTools) -> None:
    """A small model will sometimes invent a reason; that must not break the run."""
    assert tools.flag_for_review("h_1", "SOMETHING_MADE_UP")["reason"] == "OTHER"
    assert tools.flag_for_review("h_1", "DUPLICATE")["reason"] == "DUPLICATE"
