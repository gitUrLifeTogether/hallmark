"""An argument must be the right kind of value, not merely a handle.

A planner that skipped extraction passed the vendor's account-number handle in the amount
slot. Both are digit strings, so it resolved cleanly and reached the policy engine, which
read a twelve-digit account as paise — ninety-one crore — and refused a ₹45,000 invoice for
exceeding an approval limit. The engine answered correctly; it was asked the wrong question.

Typed values are what make declassification safe to do at all, so a slot that accepts any
type undermines the design. It failed safe that time, and the direction of the error was
luck rather than design.
"""

from __future__ import annotations

import pytest

from hallmark.application.scripted_run import RegexInvoiceReader
from hallmark.domain.tools import ReasonCode, ToolOutcome
from tests.unit.helpers import build_tools_for_test

BODY_EMAIL = "email-01"


@pytest.fixture
def prepared() -> tuple[object, dict, dict]:
    """A run that has read, extracted and looked up, ready to attempt a payment."""
    tools = build_tools_for_test()
    tools._reader = RegexInvoiceReader()

    listing = tools.list_inbox()
    handle = next(
        entry["email_handle"]
        for entry in listing["emails"]
        if tools._email_by_handle[entry["email_handle"]] == BODY_EMAIL
    )
    email = tools.read_email(handle)
    fields = tools.extract_invoice(email["body_handle"])["fields"]
    vendor = tools.lookup_vendor(fields["gstin"]["handle"], email["sender_domain_handle"])
    return tools, fields, vendor


def test_the_right_handles_are_accepted(prepared: tuple) -> None:
    tools, fields, vendor = prepared

    result = tools._pep.pay_vendor(
        tools.run,
        vendor_handle=vendor["vendor_handle"],
        account_handle=vendor["account_on_file_handle"],
        amount_handle=fields["amount"]["handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=True,
    )

    assert result.reason_code is not ReasonCode.ARG_WRONG_TYPE


def test_an_account_number_is_not_an_amount(prepared: tuple) -> None:
    """The exact confusion that produced a wrong verdict on a real run."""
    tools, fields, vendor = prepared

    result = tools._pep.pay_vendor(
        tools.run,
        vendor_handle=vendor["vendor_handle"],
        account_handle=vendor["account_on_file_handle"],
        amount_handle=vendor["account_on_file_handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=True,
    )

    assert result.status is ToolOutcome.DENIED
    assert result.reason_code is ReasonCode.ARG_WRONG_TYPE


def test_an_amount_is_not_an_invoice_number(prepared: tuple) -> None:
    """The mix-up behind the original enforcement error, now named rather than thrown."""
    tools, fields, vendor = prepared

    result = tools._pep.pay_vendor(
        tools.run,
        vendor_handle=vendor["vendor_handle"],
        account_handle=vendor["account_on_file_handle"],
        amount_handle=fields["amount"]["handle"],
        invoice_handle=fields["amount"]["handle"],
        vendor_match_verified=True,
    )

    assert result.reason_code is ReasonCode.ARG_WRONG_TYPE


def test_an_invoice_number_is_not_an_account(prepared: tuple) -> None:
    tools, fields, vendor = prepared

    result = tools._pep.pay_vendor(
        tools.run,
        vendor_handle=vendor["vendor_handle"],
        account_handle=fields["invoice_number"]["handle"],
        amount_handle=fields["amount"]["handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=True,
    )

    assert result.reason_code is ReasonCode.ARG_WRONG_TYPE


def test_the_refusal_points_at_the_step_that_was_skipped(prepared: tuple) -> None:
    """A planner that substituted a handle usually never extracted one to begin with."""
    tools, fields, vendor = prepared

    result = tools._pep.pay_vendor(
        tools.run,
        vendor_handle=vendor["vendor_handle"],
        account_handle=vendor["account_on_file_handle"],
        amount_handle=vendor["account_on_file_handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=True,
    )

    assert "extract_invoice" in result.suggested_next


def test_a_wrong_type_is_refused_before_any_policy_is_consulted(prepared: tuple) -> None:
    """The point of refusing early: no policy should have to reason about nonsense."""
    tools, fields, vendor = prepared

    result = tools._pep.pay_vendor(
        tools.run,
        vendor_handle=vendor["vendor_handle"],
        account_handle=vendor["account_on_file_handle"],
        amount_handle=vendor["account_on_file_handle"],
        invoice_handle=fields["invoice_number"]["handle"],
        vendor_match_verified=True,
    )

    assert result.determining_policies == ()


def test_a_bank_change_is_reported_as_a_fact_not_left_to_the_planner() -> None:
    """Comparing two masked strings is a poor thing to ask a small model to do.

    Left to the planner it got the comparison wrong often enough to decide the outcome of
    a run by chance: the same attack came back hard-denied twice and merely pending once,
    because that time the planner paid the account on file and the account rule was never
    reached. The comparison is a fact about two values, so it is computed.
    """
    tools = build_tools_for_test()
    tools._reader = RegexInvoiceReader()

    listing = tools.list_inbox()
    # The bank-change attack. It is email 14 in the story and email-19 in the fixture,
    # which is exactly the kind of mismatch worth naming rather than assuming.
    handle = next(
        entry["email_handle"]
        for entry in listing["emails"]
        if tools._email_by_handle[entry["email_handle"]] == "email-19"
    )
    email = tools.read_email(handle)
    fields = tools.extract_invoice(email["body_handle"])["fields"]
    vendor = tools.lookup_vendor(fields["gstin"]["handle"], email["sender_domain_handle"])

    assert vendor["invoice_proposes_new_account"] is True


def test_an_invoice_using_the_account_on_file_is_not_a_bank_change() -> None:
    tools = build_tools_for_test()
    tools._reader = RegexInvoiceReader()

    listing = tools.list_inbox()
    handle = next(
        entry["email_handle"]
        for entry in listing["emails"]
        if tools._email_by_handle[entry["email_handle"]] == BODY_EMAIL
    )
    email = tools.read_email(handle)
    fields = tools.extract_invoice(email["body_handle"])["fields"]
    vendor = tools.lookup_vendor(fields["gstin"]["handle"], email["sender_domain_handle"])

    assert vendor["invoice_proposes_new_account"] is False


def test_prepare_payment_returns_everything_a_payment_needs() -> None:
    """One call instead of three, because a small model skipped one of the three.

    A run went read_email, flag_for_review, extract_invoice, pay_vendor -- never looking
    the vendor up -- then invented a handle for the account and was refused for naming one
    that does not exist. No wording of the procedure fixed that, so the procedure stopped
    being something the model has to remember.
    """
    tools = build_tools_for_test()
    tools._reader = RegexInvoiceReader()
    handle = next(
        entry["email_handle"]
        for entry in tools.list_inbox()["emails"]
        if tools._email_by_handle[entry["email_handle"]] == BODY_EMAIL
    )

    prepared = tools.prepare_payment(handle)

    for needed in ("vendor_handle", "account_on_file_handle", "invoice_proposes_new_account"):
        assert needed in prepared, needed
    for field in ("amount", "invoice_number", "bank_account"):
        assert field in prepared["fields"], field


def test_prepare_payment_reports_an_unreadable_email_rather_than_half_a_result() -> None:
    """Half a result is what lets a planner carry on and invent the missing part."""
    tools = build_tools_for_test()
    tools._reader = RegexInvoiceReader()

    prepared = tools.prepare_payment("h_does_not_exist")

    assert "error" in prepared
    assert "vendor_handle" not in prepared


def test_the_model_is_offered_only_the_composed_tool() -> None:
    """The three separate calls still exist for the scripted planner and these tests.

    They are no longer on the model's surface, because an order that cannot be expressed
    cannot be got wrong.
    """
    from hallmark.application.planner import build_strands_tools

    tools = build_tools_for_test()
    names = {
        getattr(t, "tool_name", getattr(t, "__name__", "")) for t in build_strands_tools(tools)
    }

    assert "prepare_payment" in names
    assert {"read_email", "extract_invoice", "lookup_vendor"} & names == set()


def prepared_for(email_id: str):
    tools = build_tools_for_test()
    tools._reader = RegexInvoiceReader()
    handle = next(
        entry["email_handle"]
        for entry in tools.list_inbox()["emails"]
        if tools._email_by_handle[entry["email_handle"]] == email_id
    )
    tools.prepare_payment(handle)
    return tools


def test_the_planner_names_an_account_rather_than_spelling_four_handles() -> None:
    """The last thing a 1.7b model had to get right, and could not.

    It typed a value where a handle belonged, and the call was refused before any policy
    could consider it — which on screen reads as the system blocking a legitimate invoice.
    Handles are unchanged underneath; the enforcement point still receives and judges them.
    """
    result = prepared_for(BODY_EMAIL).pay_prepared("on_file")

    assert result["status"] == "EXECUTED"
    assert result["determining_policies"] == ["pay-permit-within-mandate"]


def test_naming_the_invoice_account_still_reaches_the_account_rule() -> None:
    """The choice that matters stays with the planner, and is still judged."""
    result = prepared_for("email-19").pay_prepared("from_invoice")

    assert result["status"] == "DENIED"
    assert result["reason_code"] == "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    assert "pay-account-must-be-master" in result["determining_policies"]


def test_paying_before_preparing_says_so() -> None:
    tools = build_tools_for_test()

    result = tools.pay_prepared("on_file")

    assert result["reason_code"] == "NOTHING_PREPARED"
    assert "prepare_payment" in result["suggested_next"]


def test_an_unrecognised_account_word_falls_back_to_the_record() -> None:
    """A model that invents a third word must not accidentally pay the invoice's account.

    Defaulting to the vendor master is the safe direction: the worst case is a payment the
    policies then judge on trusted provenance, never an untrusted account slipping through
    on a typo.
    """
    result = prepared_for(BODY_EMAIL).pay_prepared("whatever")

    assert result["status"] == "EXECUTED"


def test_a_payment_with_no_account_named_follows_the_document() -> None:
    """The model sometimes omits the argument entirely, and the run must still mean something.

    Falling back to the account on file would be the safer-looking choice and the wrong
    one: it would quietly make the agent more careful than the agent being demonstrated,
    and the attack would never reach the rule that stops it. Following the document is what
    a credulous accounts payable agent does, and the enforcement point decides either way.
    """
    assert prepared_for("email-19").pay_prepared()["reason_code"] == (
        "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    )


def test_a_legitimate_invoice_with_no_account_named_still_executes() -> None:
    """Following the document is not the same as being reckless: when the invoice names the
    account already on file, that is the account it names."""
    assert prepared_for(BODY_EMAIL).pay_prepared()["status"] == "EXECUTED"


def test_a_refusal_before_the_enforcement_point_is_recorded_as_an_attempt() -> None:
    """Otherwise a summary reports it as no payment attempted, which credits a defence
    that was never tested — the fault that once inflated the bench."""
    tools = build_tools_for_test()

    tools.pay_prepared("on_file")

    assert len(tools.attempts) == 1
    assert tools.attempts[0]["reason_code"] == "NOTHING_PREPARED"


def test_the_decisive_policy_is_listed_first() -> None:
    """The card's heading and its first policy must agree.

    Cedar returns the policies that denied in its own order. A verdict headed
    ACCOUNT_NOT_FROM_VENDOR_MASTER that then lists pay-vendor-match-required first invites
    exactly the misreading REASON_PRECEDENCE exists to prevent — that a human could approve
    it — reappearing one layer up, in the presentation.
    """
    result = prepared_for("email-19").pay_prepared("from_invoice")

    assert result["reason_code"] == "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    assert result["determining_policies"][0] == "pay-account-must-be-master"


def test_policies_outside_the_precedence_table_are_kept_not_dropped() -> None:
    """Ordering must not lose one. Every policy that denied is still reported."""
    result = prepared_for("email-19").pay_prepared("from_invoice")

    assert set(result["determining_policies"]) >= {
        "pay-account-must-be-master",
        "pay-vendor-match-required",
    }
