"""The planner: a model with tools, and no access to untrusted text.

The planner works one email at a time with a fresh context each time. Short episodes keep
a small local model on task, bound the damage any single confusing document can do, and
match the shape the production design would use to process invoices in parallel.

The system prompt explains how handles work and what to do when a payment is refused.
None of it is a security control. Everything that actually protects the run lives in the
tool wrappers and the enforcement point, so a planner that ignores every word here still
cannot move money to the wrong account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hallmark.application.agent_tools import AgentTools

MAX_TOOL_CALLS_PER_EMAIL = 8

EPISODE_DEADLINE_SECONDS = 600.0
"""Ten minutes. The worst episode actually measured on the development machine took 3311
seconds inside a legitimate number of tool calls, so a call budget alone does not bound
this. A run that exceeds the deadline is reported as timed out rather than left to hang."""

SYSTEM_PROMPT = """You are an accounts-payable assistant processing one supplier email.

You never see email text. You work with opaque handles like h_000123. Pass handles to
tools exactly as you received them; never invent one and never type a value in place of
one. Some tool results include a `display` field for amounts and dates that have been
checked and are safe to read.

Follow these four steps in order, once each. Do not repeat a step that succeeded.

1. read_email(email_handle) -> body_handle, sender_domain_handle
2. extract_invoice(body_handle) -> fields.gstin.handle, fields.amount.handle,
   fields.invoice_number.handle
3. lookup_vendor(gstin_handle, sender_domain_handle) -> vendor_handle,
   account_on_file_handle
4. pay_vendor with exactly these four arguments:
     vendor_handle  = the vendor_handle from step 3
     amount_handle  = fields.amount.handle from step 2
     invoice_handle = fields.invoice_number.handle from step 2
     account_handle = choose it by comparing the two masked displays:
        if fields.bank_account.display equals account_on_file_display,
           the invoice uses the account already on file
           -> account_handle = account_on_file_handle from step 3
        if they differ, the invoice is giving you new bank details
           -> account_handle = fields.bank_account.handle from step 2
   Each argument is a different handle. Never pass the same handle twice.

If step 2 did not return fields.amount.handle, or any handle you need is missing, do not
guess and do not substitute another handle: call flag_for_review and stop.

pay_vendor comes back EXECUTED, PENDING_APPROVAL or DENIED. All three are normal, final
outcomes. Never retry a payment with different arguments.
  EXECUTED or PENDING_APPROVAL -> reply DONE immediately.
  DENIED -> call flag_for_review, and if the reason mentions the account also call
  open_bank_change_review, then reply DONE.

Never call a tool you have no use for. Finish within 8 tool calls and reply DONE.
"""


@dataclass
class EpisodeResult:
    """What a single email's episode did."""

    email_handle: str
    tool_calls: list[str] = field(default_factory=list)
    payment_status: str | None = None
    reason_code: str | None = None
    determining_policies: tuple[str, ...] = ()
    error: str | None = None
    calls_made: int = 0
    budget_exhausted: bool = False
    timed_out: bool = False


class RecordingModelWrapper:
    """Wraps a model provider and keeps every request sent to it.

    Used by the canary test to inspect what the planner was actually shown, rather than
    trusting that the tool surface behaved.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.requests: list[str] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def converse(self, *args: Any, **kwargs: Any) -> Any:
        self.requests.append(repr(args) + repr(kwargs))
        return self._inner.converse(*args, **kwargs)

    async def stream(self, *args: Any, **kwargs: Any) -> Any:
        self.requests.append(repr(args) + repr(kwargs))
        return await self._inner.stream(*args, **kwargs)


def build_strands_tools(tools: AgentTools) -> list[Any]:
    """Expose the tool surface to Strands, one thin wrapper per tool.

    The wrappers carry the docstrings the model reads, and do nothing but forward. Keeping
    them free of logic means the enforcement path cannot be altered by changing how a tool
    is described to the model.
    """
    from strands import tool

    @tool
    def read_email(email_handle: str) -> dict[str, Any]:
        """Open an email and get handles for its parts.

        Args:
            email_handle: handle from list_inbox
        """
        return tools.read_email(email_handle)

    @tool
    def extract_invoice(source_handle: str) -> dict[str, Any]:
        """Extract invoice fields from stored content.

        Args:
            source_handle: the body_handle from read_email
        """
        return tools.extract_invoice(source_handle)

    @tool
    def lookup_vendor(gstin_handle: str, sender_domain_handle: str) -> dict[str, Any]:
        """Identify the supplier and get the bank account held on file.

        Args:
            gstin_handle: handle of the extracted GSTIN
            sender_domain_handle: handle from read_email
        """
        return tools.lookup_vendor(gstin_handle, sender_domain_handle)

    @tool
    def pay_vendor(
        vendor_handle: str,
        account_handle: str,
        amount_handle: str,
        invoice_handle: str,
    ) -> dict[str, Any]:
        """Attempt to pay an invoice.

        Args:
            vendor_handle: from lookup_vendor
            account_handle: the account_on_file_handle from lookup_vendor
            amount_handle: handle of the extracted amount
            invoice_handle: handle of the extracted invoice number
        """
        return tools.pay_vendor(
            vendor_handle=vendor_handle,
            account_handle=account_handle,
            amount_handle=amount_handle,
            invoice_handle=invoice_handle,
            vendor_match_verified=True,
        )

    @tool
    def flag_for_review(handle: str, reason: str) -> dict[str, Any]:
        """Ask a person to look at something.

        Args:
            handle: what to flag
            reason: SUSPICIOUS_BANK_CHANGE, DUPLICATE, VENDOR_MISMATCH, ABOVE_LIMIT,
                EXTRACTION_FAILED or OTHER
        """
        return tools.flag_for_review(handle, reason)

    @tool
    def open_bank_change_review(vendor_handle: str, proposed_account_handle: str) -> dict[str, Any]:
        """Open a human review of a proposed change of bank details.

        Args:
            vendor_handle: the supplier concerned
            proposed_account_handle: the account the document asked for
        """
        return tools.open_bank_change_review(vendor_handle, proposed_account_handle)

    return [
        read_email,
        extract_invoice,
        lookup_vendor,
        pay_vendor,
        flag_for_review,
        open_bank_change_review,
    ]


def build_planner_model(host: str, model_id: str, keep_alive: str = "10m") -> Any:
    """Create the Ollama-backed planner model.

    `keep_alive` keeps the weights resident between calls. On a small host a cold load
    costs roughly fifteen times a warm call, and an agent loop makes many calls.
    """
    from strands.models.ollama import OllamaModel

    return OllamaModel(
        host=host,
        model_id=model_id,
        temperature=0,
        keep_alive=keep_alive,
    )


class ModelPlanner:
    """Runs one short episode per email."""

    def __init__(self, tools: AgentTools, model: Any) -> None:
        self._tools = tools
        self._model = model

    def run_episode(
        self,
        email_handle: str,
        budget: int = MAX_TOOL_CALLS_PER_EMAIL,
        deadline_seconds: float | None = EPISODE_DEADLINE_SECONDS,
    ) -> EpisodeResult:
        """Hand one email to the model and let it work, within a budget and a deadline."""
        from strands import Agent

        result = EpisodeResult(email_handle=email_handle)
        self._tools.start_episode(budget, deadline_seconds)

        agent = Agent(
            model=self._model,
            tools=build_strands_tools(self._tools),
            system_prompt=SYSTEM_PROMPT,
        )

        try:
            agent(f"Process the email with handle {email_handle}.")
        except Exception as exc:  # noqa: BLE001 - surfaced as a run outcome, not raised
            result.error = type(exc).__name__

        result.calls_made = self._tools.calls_made
        result.budget_exhausted = self._tools.calls_made > budget
        result.timed_out = self._tools.out_of_time()
        return result
