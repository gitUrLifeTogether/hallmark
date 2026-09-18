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
