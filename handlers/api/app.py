"""The console API. A composition root, so it wires adapters and does nothing clever.

Routing is a small table rather than a framework: the whole surface is a handful of
endpoints, and a Lambda that imports a web framework pays for it on every cold start.

Errors are mapped to status codes here and nowhere else. Nothing derived from untrusted
content reaches a response body, so a client never receives attacker-influenced text even
in an error.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC
from typing import Any

from hallmark.adapters.auth.tokens import Principal, issue_token, verify_token
from hallmark.adapters.dynamodb.approvals import DynamoApprovalStore
from hallmark.application.approvals import ApprovalService
from hallmark.domain.errors import (
    AuthenticationError,
    Conflict,
    HallmarkError,
    NotFound,
    ValidationError,
)

STATUS_FOR_ERROR: dict[type[HallmarkError], int] = {
    AuthenticationError: 401,
    ValidationError: 400,
    NotFound: 404,
    Conflict: 409,
}

#: Demo identities. A stand-in for a user directory, not a credential store: the point of
#: the login endpoint is to mint a token carrying a role, so approval limits can be tested.
DEMO_USERS: dict[str, str] = {
    "ananya": "AP_LEAD",
    "vikram": "CONTROLLER",
    "judge": "JUDGE",
}


class Clock:
    def now_iso(self) -> str:
        from datetime import datetime

        return datetime.now(UTC).isoformat()


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _error(code: str, message: str, status: int) -> dict[str, Any]:
    return _response(status, {"error": {"code": code, "message": message}})


def _secret() -> str:
    secret = os.environ.get("JWT_SIGNING_SECRET", "")
    if not secret:
        raise HallmarkError("JWT_SIGNING_SECRET is not configured")
    return secret


def _approval_service() -> ApprovalService:
    store = DynamoApprovalStore(
        os.environ["APPROVALS_TABLE"], os.environ.get("TENANT_ID", "kestrel")
    )
    return ApprovalService(store, Clock())


def _principal(event: dict[str, Any]) -> Principal:
    """Identify the caller, or refuse.

    The role in the token decides which amounts may be approved, so this is verified
    rather than read.
    """
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    header = headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise AuthenticationError("authentication failed")

    try:
        return verify_token(header[7:].strip(), _secret())
    except ValidationError as exc:
        # Collapse every token fault into one answer, so nothing is learned from which.
        raise AuthenticationError("authentication failed") from exc


# ------------------------------------------------------------------ endpoints


def post_login(event: dict[str, Any]) -> dict[str, Any]:
    """Mint a demo token. Present only because there is no identity provider here."""
    body = json.loads(event.get("body") or "{}")
    user_id = str(body.get("userId", "")).strip()

    role = DEMO_USERS.get(user_id)
    if role is None:
        raise NotFound("unknown demo user")

    principal = Principal(user_id, role, os.environ.get("TENANT_ID", "kestrel"))
    return _response(200, {"token": issue_token(principal, _secret()), "role": role})


def get_approvals(event: dict[str, Any]) -> dict[str, Any]:
    _principal(event)
    store = DynamoApprovalStore(
        os.environ["APPROVALS_TABLE"], os.environ.get("TENANT_ID", "kestrel")
    )
    return _response(200, {"approvals": [a.public_view() for a in store.pending()]})


def post_approval_decision(event: dict[str, Any]) -> dict[str, Any]:
    """Decide an escalation.

    The approver's role comes from their verified token, never from the request body. A
    client that could name its own role could approve anything.
    """
    principal = _principal(event)
    approval_id = (event.get("pathParameters") or {}).get("approvalId", "")
    body = json.loads(event.get("body") or "{}")

    result = _approval_service().decide(
        approval_id=approval_id,
        decision=str(body.get("decision", "")),
        approver_id=principal.user_id,
        approver_role=principal.role,
    )
    return _response(200, result)


def get_health(event: dict[str, Any]) -> dict[str, Any]:
    return _response(
        200,
        {
            "status": "ok",
            "service": "hallmark",
            "stage": os.environ.get("STAGE", "unknown"),
            "tenant": os.environ.get("TENANT_ID", "unknown"),
        },
    )


ROUTES: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {
    ("GET", "/health"): get_health,
    ("POST", "/auth/login"): post_login,
    ("GET", "/approvals"): get_approvals,
    ("POST", "/approvals/{approvalId}/decision"): post_approval_decision,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = event.get("httpMethod", "")
    resource = event.get("resource") or event.get("path", "")

    route = ROUTES.get((method, resource))
    if route is None:
        return _error("NOT_FOUND", "no such endpoint", 404)

    try:
        return route(event)
    except HallmarkError as exc:
        status = STATUS_FOR_ERROR.get(type(exc), 500)
        if isinstance(exc, AuthenticationError):
            return _error("UNAUTHORIZED", "authentication failed", 401)
        code = type(exc).__name__.replace("Error", "").upper() or "ERROR"
        return _error(code, str(exc), status)
    except Exception:
        # Never leak an internal message; the details are in the logs.
        return _error("INTERNAL", "request failed", 500)
