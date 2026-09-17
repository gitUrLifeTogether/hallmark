"""Locally signed JWTs, standing in for a hosted identity provider.

This is a demo substitute, not a security feature, and the difference matters. It proves
the *shape* — an approver's identity and role reach the authorization decision — while a
real deployment would verify tokens from a managed provider. The signing secret comes from
the environment and never has a default, so a missing configuration is a startup failure
rather than a silently insecure deployment.

Approver roles are load-bearing: who may approve which amount is part of the decision, so
a forged role would matter even in the demo. Hence a real HMAC, verified, rather than a
decoded-but-unchecked payload.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from hallmark.domain.errors import ValidationError

ALGORITHM = "HS256"
DEFAULT_TTL_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class Principal:
    """Who is making a request, and what they are allowed to approve."""

    user_id: str
    role: str
    tenant_id: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(message: bytes, secret: str) -> str:
    return _b64url_encode(hmac.new(secret.encode(), message, hashlib.sha256).digest())


def issue_token(
    principal: Principal,
    secret: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """Mint a token for a demo user."""
    if not secret:
        raise ValidationError("a signing secret is required")

    issued_at = int(time.time()) if now is None else now
    header = {"alg": ALGORITHM, "typ": "JWT"}
    claims = {
        "sub": principal.user_id,
        "role": principal.role,
        "tenant": principal.tenant_id,
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
    }

    header_segment = _b64url_encode(json.dumps(header).encode())
    claims_segment = _b64url_encode(json.dumps(claims).encode())
    segments = f"{header_segment}.{claims_segment}"

    return f"{segments}.{_sign(segments.encode(), secret)}"


def verify_token(token: str, secret: str, now: int | None = None) -> Principal:
    """Verify a token and return who it belongs to.

    Raises `ValidationError` on anything wrong: a bad signature, a bad shape, or an expired
    token. Callers turn that into a 401 without distinguishing the cases, since telling an
    attacker *which* part failed is free information.
    """
    if not secret:
        raise ValidationError("a signing secret is required")

    parts = token.split(".")
    if len(parts) != 3:
        raise ValidationError("malformed token")

    header_segment, claims_segment, signature = parts
    expected = _sign(f"{header_segment}.{claims_segment}".encode(), secret)

    # Constant-time comparison: a timing difference here would leak the signature.
    if not hmac.compare_digest(signature, expected):
        raise ValidationError("bad signature")

    try:
        claims: dict[str, Any] = json.loads(_b64url_decode(claims_segment))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("malformed claims") from exc

    current = int(time.time()) if now is None else now
    if int(claims.get("exp", 0)) <= current:
        raise ValidationError("token expired")

    for field in ("sub", "role", "tenant"):
        if not claims.get(field):
            raise ValidationError("incomplete claims")

    return Principal(
        user_id=str(claims["sub"]),
        role=str(claims["role"]),
        tenant_id=str(claims["tenant"]),
    )
