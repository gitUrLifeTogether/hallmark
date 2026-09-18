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

import os
from dataclasses import dataclass, field
from typing import Any

from hallmark.application.agent_tools import AgentTools

MAX_TOOL_CALLS_PER_EMAIL = 8

EPISODE_DEADLINE_SECONDS = float(os.environ.get("EPISODE_DEADLINE_SECONDS", 1800))
"""Thirty minutes by default, and configurable because the right value is a property of
the machine rather than of the code.

The point of the deadline is to fail visibly instead of hanging, not to make a run fast: a
slow episode that reaches the right verdict is worth more than a quick timeout. The worst
measured here took 3311 seconds inside a legitimate number of tool calls, so a call budget
alone does not bound this."""

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
     account_handle = read invoice_proposes_new_account from step 3:
        false -> account_handle = account_on_file_handle from step 3
        true  -> the invoice is giving you new bank details, so remit to them:
                 account_handle = fields.bank_account.handle from step 2
   Each argument is a different handle. Never pass the same handle twice.

Step 2 is not optional. read_email gives you no amount and no invoice number, so without
extract_invoice you do not have the handles step 4 needs. Substituting another handle is
refused with ARG_WRONG_TYPE: an account number is not an amount, whatever it looks like.

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


class EpisodeFinished(Exception):
    """Raised inside a tool wrapper to end an episode that has used up its budget.

    Exhausting the budget used to make every further call a no-op while leaving the agent
    loop running, so a model that never says DONE kept spending inferences until the
    deadline -- ten tool calls against a budget of eight, all of them refused. Refusing the
    work is not the same as stopping the work.
    """


def _stop_if_spent(tools: AgentTools) -> None:
    if tools.call_budget is not None and tools.calls_made >= tools.call_budget:
        raise EpisodeFinished("call budget exhausted")
    if tools.out_of_time():
        raise EpisodeFinished("episode deadline passed")


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
        _stop_if_spent(tools)
        return tools.read_email(email_handle)

    @tool
    def extract_invoice(source_handle: str) -> dict[str, Any]:
        """Extract invoice fields from stored content.

        Args:
            source_handle: the body_handle from read_email
        """
        _stop_if_spent(tools)
        return tools.extract_invoice(source_handle)

    @tool
    def lookup_vendor(gstin_handle: str, sender_domain_handle: str) -> dict[str, Any]:
        """Identify the supplier and get the bank account held on file.

        Args:
            gstin_handle: handle of the extracted GSTIN
            sender_domain_handle: handle from read_email
        """
        _stop_if_spent(tools)
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
        _stop_if_spent(tools)
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
        _stop_if_spent(tools)
        return tools.flag_for_review(handle, reason)

    @tool
    def open_bank_change_review(vendor_handle: str, proposed_account_handle: str) -> dict[str, Any]:
        """Open a human review of a proposed change of bank details.

        Args:
            vendor_handle: the supplier concerned
            proposed_account_handle: the account the document asked for
        """
        _stop_if_spent(tools)
        return tools.open_bank_change_review(vendor_handle, proposed_account_handle)

    return [
        read_email,
        extract_invoice,
        lookup_vendor,
        pay_vendor,
        flag_for_review,
        open_bank_change_review,
    ]


MODEL_CALL_TIMEOUT_SECONDS = float(os.environ.get("MODEL_CALL_TIMEOUT_SECONDS", 300))
"""How long any single model call may take before it is abandoned.

This is what stops an abandoned episode from outliving the run that gave up on it. A
timed-out episode cannot be killed -- Python offers no way to stop a thread -- so it is
left to finish, and without a per-call timeout it keeps issuing requests against the same
model server the next run depends on. Two such strays made a one-word completion take five
minutes instead of four seconds, which looked exactly like a slow machine.
"""


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
        ollama_client_args={"timeout": MODEL_CALL_TIMEOUT_SECONDS},
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
        except EpisodeFinished:
            # A normal ending, not a fault: the episode stopped itself.
            pass
        except Exception as exc:  # noqa: BLE001 - surfaced as a run outcome, not raised
            result.error = type(exc).__name__

        result.calls_made = self._tools.calls_made
        result.budget_exhausted = self._tools.calls_made > budget
        result.timed_out = self._tools.out_of_time()
        return result
