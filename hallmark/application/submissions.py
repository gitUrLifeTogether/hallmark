"""Emails submitted from the console, for a live run.

A submission is attacker-controlled by definition — anyone typing into the form is playing
the attacker, which is the point of the feature. So it is treated exactly like a fixture
email: stored whole, labelled `EXTERNAL_EMAIL`, and never handed to the planner as text.

Nothing here interprets the content. Validation is about size and shape only, because a
check that tried to judge whether a submission "looks malicious" would be the model-as-
security-boundary mistake in a new place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from hallmark.domain.errors import NotFound, ValidationError

MAX_SUBJECT = 300
MAX_BODY = 50_000
MAX_ATTACHMENT = 50_000
MAX_SENDER = 320
"""The longest address RFC 5321 permits, so a valid one is never refused for length."""


@dataclass(frozen=True)
class Submission:
    """One email typed into the console, awaiting processing."""

    run_id: str
    sender: str
    subject: str
    body: str
    attachment_text: str = ""

    def as_item(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "sender": self.sender,
            "subject": self.subject,
            "body": self.body,
            "attachmentText": self.attachment_text,
        }

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> Submission:
        return cls(
            run_id=str(item["runId"]),
            sender=str(item.get("sender", "")),
            subject=str(item.get("subject", "")),
            body=str(item.get("body", "")),
            attachment_text=str(item.get("attachmentText", "")),
        )


def _field(raw: Any, name: str, limit: int, *, required: bool) -> str:
    text = str(raw or "").strip()
    if required and not text:
        raise ValidationError(f"{name} is required")
    if len(text) > limit:
        raise ValidationError(f"{name} is longer than {limit} characters")
    return text


def parse_submission(run_id: str, body: dict[str, Any]) -> Submission:
    """Validate a request body into a submission.

    Size limits only. A submission is meant to be hostile, so the content is never
    inspected for intent here or anywhere else.
    """
    return Submission(
        run_id=run_id,
        sender=_field(body.get("sender"), "sender", MAX_SENDER, required=True),
        subject=_field(body.get("subject"), "subject", MAX_SUBJECT, required=False),
        body=_field(body.get("body"), "body", MAX_BODY, required=True),
        attachment_text=_field(
            body.get("attachmentText"), "attachmentText", MAX_ATTACHMENT, required=False
        ),
    )


class SubmissionStore(Protocol):
    """Where a submission waits between the API accepting it and the worker running it."""

    def put(self, submission: Submission, status: str) -> None: ...
    def get(self, run_id: str) -> tuple[Submission, str]: ...
    def set_status(
        self, run_id: str, status: str, summary: dict[str, Any] | None = None
    ) -> None: ...
    def status_of(self, run_id: str) -> dict[str, Any]: ...


class InMemorySubmissionStore:
    """For tests and for running the worker without a deployed stack."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def put(self, submission: Submission, status: str) -> None:
        self.items[submission.run_id] = {**submission.as_item(), "status": status}

    def get(self, run_id: str) -> tuple[Submission, str]:
        item = self.items.get(run_id)
        if item is None:
            raise NotFound("no such run")
        return Submission.from_item(item), str(item.get("status", "QUEUED"))

    def set_status(self, run_id: str, status: str, summary: dict[str, Any] | None = None) -> None:
        item = self.items.get(run_id)
        if item is None:
            raise NotFound("no such run")
        item["status"] = status
        if summary is not None:
            item["summary"] = summary

    def status_of(self, run_id: str) -> dict[str, Any]:
        item = self.items.get(run_id)
        if item is None:
            raise NotFound("no such run")
        # The body is deliberately absent: it is untrusted text, and the status endpoint
        # is polled by the browser. The console renders content through the safe renderer
        # or not at all.
        return {
            "runId": run_id,
            "status": item.get("status", "QUEUED"),
            "summary": item.get("summary"),
        }
