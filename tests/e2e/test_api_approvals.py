"""End to end against the deployed stack, over HTTP.

Everything here goes through the real API: a real token, a real Lambda, a real table.
Nothing is stubbed, because the faults this catches are the ones unit tests cannot see —
a role read from a request body instead of a verified token, a task token serialised into
a response, or two approvals both winning because the write was not conditional.

Opt-in (`-m localstack`): needs the stack deployed and seeded.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

import pytest

from hallmark.adapters.dynamodb.approvals import DynamoApprovalStore
from hallmark.adapters.memory.stores import FixedClock
from hallmark.application.approvals import ApprovalService
from hallmark.config import Settings

pytestmark = pytest.mark.localstack

TENANT = "kestrel"
UNDER_AP_LIMIT = 15_000_000
OVER_AP_LIMIT = 38_000_000


def api_base() -> str:
    base = os.environ.get("HALLMARK_API_BASE")
    if not base:
        pytest.skip("HALLMARK_API_BASE is not set; deploy the stack first")
    return base.rstrip("/")


def call(
    method: str, path: str, body: dict | None = None, token: str | None = None
) -> tuple[int, dict]:
    """One HTTP call, returning the status and the parsed body."""
    request = urllib.request.Request(
        f"{api_base()}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read() or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or "{}")


def login(user_id: str) -> str:
    status, body = call("POST", "/auth/login", {"userId": user_id})
    assert status == 200, body
    return str(body["token"])


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(
        {
            "AWS_ENDPOINT_URL": os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
            "AWS_DEFAULT_REGION": "ap-south-1",
            "TENANT_ID": TENANT,
        }
    )


@pytest.fixture
def pending(settings: Settings):
    """Create a fresh escalation directly, then decide it through the API."""
    store = DynamoApprovalStore(os.environ["APPROVALS_TABLE"], TENANT, settings)
    service = ApprovalService(store, FixedClock())

    def make(amount: int) -> str:
        approval_id = f"apr-{uuid.uuid4().hex[:10]}"
        service.request(
            approval_id=approval_id,
            run_id="run-e2e",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            tool="pay_vendor",
            amount_paise=amount,
            arguments={"account": "h_acc"},
            task_token=f"secret-token-{uuid.uuid4().hex}",
        )
        return approval_id

    return make


def test_the_service_is_reachable() -> None:
    status, body = call("GET", "/health")
    assert status == 200
    assert body["status"] == "ok"


def test_listing_approvals_requires_a_token() -> None:
    status, _ = call("GET", "/approvals")
    assert status == 401


def test_a_forged_token_is_refused() -> None:
    status, _ = call("GET", "/approvals", token="not.a.token")
    assert status == 401


def test_the_task_token_never_crosses_the_api(pending) -> None:
    """Handing it out would hand out the ability to resume a paused workflow."""
    pending(UNDER_AP_LIMIT)
    status, body = call("GET", "/approvals", token=login("ananya"))

    assert status == 200
    assert "secret-token-" not in json.dumps(body)


def test_an_ap_lead_cannot_approve_above_their_limit(pending) -> None:
    approval_id = pending(OVER_AP_LIMIT)
    status, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "APPROVE"}, login("ananya")
    )
    assert status == 409


def test_a_controller_can_approve_what_an_ap_lead_cannot(pending) -> None:
    approval_id = pending(OVER_AP_LIMIT)

    refused, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "APPROVE"}, login("ananya")
    )
    allowed, body = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "APPROVE"}, login("vikram")
    )

    assert refused == 409
    assert allowed == 200
    assert body["status"] == "APPROVED"


def test_the_role_comes_from_the_token_not_the_request_body(pending) -> None:
    """A client that could name its own role could approve anything."""
    approval_id = pending(OVER_AP_LIMIT)
    status, _ = call(
        "POST",
        f"/approvals/{approval_id}/decision",
        {"decision": "APPROVE", "role": "CONTROLLER", "approverRole": "CONTROLLER"},
        login("ananya"),
    )
    assert status == 409, "the body must not be able to promote the caller"


def test_an_approval_can_only_be_decided_once(pending) -> None:
    """Both winning would re-run enforcement twice and could pay twice."""
    approval_id = pending(UNDER_AP_LIMIT)

    first, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "APPROVE"}, login("ananya")
    )
    second, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "APPROVE"}, login("vikram")
    )

    assert first == 200
    assert second == 409


def test_a_rejected_approval_cannot_then_be_approved(pending) -> None:
    approval_id = pending(UNDER_AP_LIMIT)

    rejected, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "REJECT"}, login("ananya")
    )
    then_approved, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": "APPROVE"}, login("ananya")
    )

    assert rejected == 200
    assert then_approved == 409


@pytest.mark.parametrize("bad", ["approve", "", "MAYBE"])
def test_only_approve_or_reject_are_accepted(pending, bad: str) -> None:
    approval_id = pending(UNDER_AP_LIMIT)
    status, _ = call(
        "POST", f"/approvals/{approval_id}/decision", {"decision": bad}, login("ananya")
    )
    assert status == 400


def test_an_unknown_approval_is_not_found() -> None:
    status, _ = call(
        "POST", "/approvals/apr-does-not-exist/decision", {"decision": "APPROVE"}, login("ananya")
    )
    assert status == 404


def test_an_error_body_carries_no_internal_detail() -> None:
    _, body = call(
        "POST", "/approvals/apr-does-not-exist/decision", {"decision": "APPROVE"}, login("ananya")
    )
    text = json.dumps(body).lower()

    assert "error" in body
    assert "traceback" not in text
    assert ".py" not in text
