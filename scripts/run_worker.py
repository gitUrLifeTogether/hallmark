"""The live run worker: drains submitted emails and processes them with the real planner.

It runs on the host rather than as a deployed function for the reason recorded in
decisions.md: packaging the agent SDK into a function is unproven here, and a model episode
takes minutes, which is far longer than an API request should live. The API therefore
accepts a submission and announces it; this worker does the work and publishes what happens
to the same bus every other part of the system publishes to.

Nothing about enforcement is special here. The worker builds the same enforcement point,
the same tools and the same policies the tests use, and the planner it drives is the real
Ollama-backed one. If this file cheated, the canary and architecture tests would still be
green, which is why it deliberately owns no security logic of its own.

Usage:  uv run python scripts/run_worker.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.hero import COMPANY, VENDORS  # noqa: E402
from hallmark.adapters.cedar_local.authorizer import CedarLocalAuthorizer  # noqa: E402
from hallmark.adapters.dynamodb.submissions import DynamoSubmissionStore  # noqa: E402
from hallmark.adapters.eventbridge.publisher import EventBridgePublisher  # noqa: E402
from hallmark.adapters.memory.stores import (  # noqa: E402
    InMemoryDecisionStore,
    InMemoryInboxRepository,
    InMemoryLedgerRepository,
    InMemoryLineageStore,
    InMemoryValueStore,
    InMemoryVendorRepository,
    SequentialIdGenerator,
    SystemClock,
)
from hallmark.adapters.ollama.reader import OllamaReader  # noqa: E402
from hallmark.application.agent_tools import AgentTools  # noqa: E402
from hallmark.application.pep import PolicyEnforcementPoint, RunContext  # noqa: E402
from hallmark.application.planner import (  # noqa: E402
    EPISODE_DEADLINE_SECONDS,
    ModelPlanner,
    build_planner_model,
)
from hallmark.application.submissions import Submission  # noqa: E402
from hallmark.config import Settings, local_boto3_client  # noqa: E402
from hallmark.domain.mandate import Mandate  # noqa: E402
from hallmark.ports.events import DomainEvent, EventType  # noqa: E402
from hallmark.ports.repositories import EmailAttachment, InboxEmail  # noqa: E402

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("PLANNER_MODEL", "qwen3:1.7b")

MANDATE = Mandate(frozenset({"pay_vendor", "send_email"}), 50_000_000, 20_000_000)
"""Matches the hero run: a ₹5,00,000 cap and a ₹2,00,000 auto-approve limit."""

VENDOR_DOMAINS = {vendor.domain.lower() for vendor in VENDORS}


def _dkim_for(sender: str) -> bool:
    """Stand in for a DKIM check, which cannot be performed on a typed-in address.

    A submission has no signature to verify, so the result is simulated: it passes only
    when the sender's domain is exactly a vendor's registered domain. That is what a real
    check would yield for a genuine sender, and it makes a lookalike domain fail, which is
    the behaviour the attack scenarios depend on.

    It is simulated, and simulated-vs-real says so. It is also not load-bearing: DKIM feeds
    `vendorMatchVerified`, which a human can override. The account rule, which nobody can
    override, does not consult it.
    """
    domain = sender.split("@")[-1].strip().lower()
    return domain in VENDOR_DOMAINS


def email_from(submission: Submission) -> InboxEmail:
    """Turn a typed submission into an inbox email the pipeline treats like any other."""
    attachments: tuple[EmailAttachment, ...] = ()
    if submission.attachment_text:
        attachments = (
            EmailAttachment(
                attachment_id=f"att_{submission.run_id}",
                filename="submitted-invoice.pdf",
                text=submission.attachment_text,
            ),
        )

    return InboxEmail(
        email_id=f"submitted-{submission.run_id}",
        sender=submission.sender,
        sender_display_name=submission.sender.split("@")[0],
        subject=submission.subject,
        body=submission.body,
        received_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dkim_pass=_dkim_for(submission.sender),
        attachments=attachments,
    )


def build_tools(run_id: str, submission: Submission, events: Any) -> tuple[AgentTools, Any, Any]:
    values = InMemoryValueStore()
    lineage = InMemoryLineageStore()
    ids = SequentialIdGenerator()
    clock = SystemClock()
    vendors = InMemoryVendorRepository(list(VENDORS))
    ledger = InMemoryLedgerRepository([])
    decisions = InMemoryDecisionStore()

    pep = PolicyEnforcementPoint(
        authorizer=CedarLocalAuthorizer.from_directory(POLICY_DIR),
        values=values,
        lineage=lineage,
        decisions=decisions,
        vendors=vendors,
        ledger=ledger,
        company=COMPANY,
        ids=ids,
        clock=clock,
        events=events,
    )
    tools = AgentTools(
        run=RunContext(run_id, "ananya", MANDATE),
        pep=pep,
        inbox=InMemoryInboxRepository([email_from(submission)]),
        vendors=vendors,
        values=values,
        lineage=lineage,
        ids=ids,
        clock=clock,
        reader=OllamaReader(OLLAMA_HOST, MODEL, keep_alive="10m"),
        events=events,
    )
    return tools, ledger, decisions


def summarise(
    decisions: Any, ledger: Any, run_id: str, attempts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The verdict, from what enforcement recorded, never from what the model said.

    Attempts are consulted as well as decisions, because a call refused on structural
    grounds -- an argument that should have been a handle and was not -- never reaches the
    policy engine and so leaves no decision record. Reporting that as "nothing was
    attempted" would credit the system with a defence it never had to make.
    """
    recorded = [d for d in decisions.for_run(run_id) if d.tool == "pay_vendor"]
    paid = len(ledger.entries())

    # An execution outranks anything after it. A small model often pays and then tries the
    # same invoice again, and the retry is correctly refused as a duplicate -- reporting
    # that refusal as the verdict would say BLOCKED about a run where the money moved.
    executed = [d for d in recorded if str(d.outcome) == "EXECUTED"]
    decisive = executed[0] if executed else (recorded[-1] if recorded else None)

    if decisive is not None:
        return {
            "verdict": str(decisive.outcome),
            "reasonCode": str(getattr(decisive, "reason_code", "")),
            "policies": list(getattr(decisive, "determining_policies", []) or []),
            "paid": paid,
        }

    tried = [a for a in (attempts or []) if a.get("tool") == "pay_vendor"]
    if tried:
        last_try = tried[-1]
        return {
            "verdict": "REFUSED_BEFORE_POLICY",
            "reasonCode": str(last_try.get("reason_code", "")),
            "policies": [],
            "paid": paid,
        }

    return {"verdict": "NO_PAYMENT_ATTEMPTED", "policies": [], "paid": paid}


WATCHDOG_GRACE_SECONDS = float(os.environ.get("WATCHDOG_GRACE_SECONDS", 300))
"""Headroom past the planner's own deadline, for a model call already in flight when it
expires. The planner stops cooperatively at its next tool call; this bounds the case where
there is no next tool call because the current one never returns."""


FOLLOW_UP_SECONDS = float(os.environ.get("FOLLOW_UP_SECONDS", 45))
"""How long to keep waiting after a payment has been decided.

Enough for the flag and the review a denial calls for. Not a limit on the planner, which
cannot be stopped from here -- a limit on how long this worker waits for one. Refusing the
planner's calls does not end its loop, and every refused call still costs an inference, so
an episode whose verdict was settled in two calls went on for forty minutes making a
sixth, seventh and eighth attempt to flag the same email.
"""


def _run_with_watchdog(planner: ModelPlanner, tools: AgentTools, handle: str) -> bool:
    """Run an episode and stop waiting once its verdict is settled.

    Returns False only if the episode ended with nothing decided. The thread is abandoned
    rather than killed, which Python does not offer: it is a daemon, its own deadline stops
    it taking further tool calls, and the per-call model timeout stops it holding the model
    server against the next run.

    Waiting for the planner to finish talking was the mistake. What the run needs is the
    decision, and that is recorded the moment the enforcement point makes it.
    """
    done = threading.Event()

    def target() -> None:
        try:
            planner.run_episode(handle)
        finally:
            done.set()

    threading.Thread(target=target, daemon=True, name="episode").start()

    deadline = time.monotonic() + EPISODE_DEADLINE_SECONDS + WATCHDOG_GRACE_SECONDS
    settled_at: float | None = None

    while time.monotonic() < deadline:
        if done.wait(2):
            return True
        if tools.payment_decided:
            if settled_at is None:
                settled_at = time.monotonic()
            elif time.monotonic() - settled_at >= FOLLOW_UP_SECONDS:
                return True
    return False


def process(run_id: str, store: Any, events: Any) -> None:
    submission, _status = store.get(run_id)
    store.set_status(run_id, "RUNNING")
    events.publish(DomainEvent(EventType.RUN_STARTED, run_id, _now(), {"model": MODEL}))

    tools, ledger, decisions = build_tools(run_id, submission, events)
    try:
        listing = tools.list_inbox()
        handle = listing["emails"][0]["email_handle"]
        planner = ModelPlanner(tools, build_planner_model(OLLAMA_HOST, MODEL))

        abandoned = not _run_with_watchdog(planner, tools, handle)
        summary = summarise(decisions, ledger, run_id, tools.attempts)

        if not abandoned:
            status = "COMPLETED"
        elif tools.payment_decided:
            # The episode was abandoned, but its verdict was settled before that: the
            # enforcement point had already decided, and the planner simply would not stop
            # talking afterwards. Calling that a timeout would report a finished decision
            # as an unfinished run.
            summary = {**summary, "plannerDidNotStop": True}
            status = "COMPLETED"
        else:
            # Nothing was decided, so there is nothing to report but the giving up.
            summary = {**summary, "timedOut": True}
            status = "TIMED_OUT"
    except Exception as exc:  # noqa: BLE001
        # A failed episode is a utility failure, never a security one: nothing executes
        # unless the enforcement point permitted it, and it is not on this path.
        logged = type(exc).__name__
        print(f"episode failed: {logged}", file=sys.stderr)
        summary = {"verdict": "EPISODE_FAILED", "error": logged, "policies": []}
        status = "FAILED"

    store.set_status(run_id, status, summary)
    events.publish(DomainEvent(EventType.RUN_COMPLETED, run_id, _now(), summary))
    print(f"{run_id}: {status} {summary.get('verdict')}")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main() -> int:
    queue_url = os.environ.get("RUN_REQUESTS_QUEUE")
    if not queue_url:
        print(
            'RUN_REQUESTS_QUEUE is not set.\nRun:  eval "$(uv run python scripts/stack_env.py)"',
            file=sys.stderr,
        )
        return 1

    settings = Settings.from_env()
    sqs = local_boto3_client("sqs", settings)
    store = DynamoSubmissionStore(os.environ["RUNS_TABLE"], os.environ.get("TENANT_ID", "kestrel"))
    events = EventBridgePublisher(os.environ["EVENT_BUS"], settings)

    print(f"run worker ready, model {MODEL}, draining {queue_url}")
    while True:
        received = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=10
        )
        for message in received.get("Messages", []):
            try:
                detail = json.loads(message["Body"]).get("detail", {})
                run_id = str(detail.get("runId", ""))
                if run_id:
                    process(run_id, store, events)
            except Exception as exc:  # noqa: BLE001
                print(f"message failed: {type(exc).__name__}", file=sys.stderr)
            finally:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])


if __name__ == "__main__":
    raise SystemExit(main())
