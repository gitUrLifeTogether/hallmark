"""Token verification. A forged role would change who can approve a payment."""

from __future__ import annotations

import pytest

from hallmark.adapters.auth.tokens import (
    Principal,
    issue_token,
    verify_token,
)
from hallmark.domain.errors import ValidationError

SECRET = "test-signing-secret"
NOW = 1_800_000_000
ANANYA = Principal(user_id="ananya", role="AP_LEAD", tenant_id="kestrel")


def test_a_token_round_trips() -> None:
    token = issue_token(ANANYA, SECRET, now=NOW)
    assert verify_token(token, SECRET, now=NOW + 60) == ANANYA


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = issue_token(ANANYA, "someone-elses-secret", now=NOW)
    with pytest.raises(ValidationError):
        verify_token(token, SECRET, now=NOW + 60)


def test_an_edited_role_invalidates_the_signature() -> None:
    """The attack this exists to stop: promoting yourself to the higher approval limit."""
    import base64
    import json

    header, claims, signature = issue_token(ANANYA, SECRET, now=NOW).split(".")
    decoded = json.loads(base64.urlsafe_b64decode(claims + "=="))
    decoded["role"] = "CONTROLLER"
    forged_claims = base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=").decode()

    with pytest.raises(ValidationError):
        verify_token(f"{header}.{forged_claims}.{signature}", SECRET, now=NOW + 60)


def test_an_expired_token_is_refused() -> None:
    token = issue_token(ANANYA, SECRET, ttl_seconds=60, now=NOW)
    with pytest.raises(ValidationError):
        verify_token(token, SECRET, now=NOW + 61)


def test_a_token_is_valid_right_up_to_expiry() -> None:
    token = issue_token(ANANYA, SECRET, ttl_seconds=60, now=NOW)
    assert verify_token(token, SECRET, now=NOW + 59).user_id == "ananya"


@pytest.mark.parametrize("bad", ["", "not-a-token", "a.b", "a.b.c.d", "...."])
def test_malformed_tokens_are_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        verify_token(bad, SECRET, now=NOW)


def test_an_empty_secret_is_refused_rather_than_accepted() -> None:
    """A missing secret must fail loudly, not sign everything with an empty key."""
    with pytest.raises(ValidationError):
        issue_token(ANANYA, "", now=NOW)
    with pytest.raises(ValidationError):
        verify_token(issue_token(ANANYA, SECRET, now=NOW), "", now=NOW)


def test_claims_missing_a_role_are_refused() -> None:
    import base64
    import json

    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    claims = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "x", "tenant": "kestrel", "exp": NOW + 99}).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    import hashlib
    import hmac

    signature = (
        base64.urlsafe_b64encode(
            hmac.new(SECRET.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )

    with pytest.raises(ValidationError):
        verify_token(f"{header}.{claims}.{signature}", SECRET, now=NOW)
