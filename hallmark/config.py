"""Typed settings from the environment, plus the LOCAL_ONLY guard.

Nothing in this project may ever touch real AWS. That rule is enforced in three places:
this module, the `Makefile` targets, and the absence of any real credentials. This module
is the code-level half — no boto3 client is constructed anywhere in the codebase except
through `local_boto3_client`, which refuses any endpoint that is not a local emulator.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from hallmark.domain.errors import ConfigurationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

#: Hostnames that count as a local AWS emulator (LocalStack, DynamoDB Local, or the
#: host as seen from inside a Lambda container started by LocalStack).
LOCAL_ENDPOINT_HOSTS: Final[frozenset[str]] = frozenset(
    {"localhost", "127.0.0.1", "localstack", "host.docker.internal"}
)

DEFAULT_REGION: Final = "ap-south-1"
DEFAULT_ENDPOINT_URL: Final = "http://localhost:4566"
DEFAULT_OLLAMA_HOST: Final = "http://localhost:11434"


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Process configuration, read once at the composition root.

    No model id, region, endpoint or secret is hardcoded anywhere else in the codebase.
    """

    local_only: bool
    aws_endpoint_url: str | None
    aws_region: str
    ollama_host: str
    planner_model: str
    reader_model: str
    planner_backend: str
    tenant_id: str
    stage: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from the environment, defaulting to the local Build It stack."""
        e: Mapping[str, str] = os.environ if env is None else env
        return cls(
            local_only=_env_bool(e, "LOCAL_ONLY", True),
            aws_endpoint_url=e.get("AWS_ENDPOINT_URL") or None,
            aws_region=e.get("AWS_DEFAULT_REGION") or DEFAULT_REGION,
            ollama_host=e.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST,
            planner_model=e.get("PLANNER_MODEL") or "qwen3:4b",
            reader_model=e.get("READER_MODEL") or "qwen3:1.7b",
            planner_backend=e.get("PLANNER_BACKEND") or "llm",
            tenant_id=e.get("TENANT_ID") or "kestrel",
            stage=e.get("STAGE") or "dev",
        )


def is_local_endpoint(endpoint_url: str | None) -> bool:
    """Return True only for URLs whose host is a known local emulator host."""
    if not endpoint_url:
        return False
    host = urlsplit(endpoint_url).hostname
    return host is not None and host.lower() in LOCAL_ENDPOINT_HOSTS


def assert_local_endpoint(endpoint_url: str | None, *, local_only: bool = True) -> None:
    """Raise `ConfigurationError` unless `endpoint_url` points at a local emulator.

    A missing endpoint is itself a failure: boto3 would silently fall back to the real
    AWS endpoints for the configured region, which is exactly what the Build It track
    forbids. The error message never includes credentials or tokens.
    """
    if not local_only:
        return
    if endpoint_url is None or endpoint_url == "":
        raise ConfigurationError(
            "AWS_ENDPOINT_URL is not set. Hallmark runs in LOCAL_ONLY mode and refuses to "
            "fall back to real AWS endpoints. Set AWS_ENDPOINT_URL=http://localhost:4566."
        )
    if not is_local_endpoint(endpoint_url):
        host = urlsplit(endpoint_url).hostname or "<unparseable>"
        raise ConfigurationError(
            f"Refusing to create an AWS client for non-local endpoint host {host!r}. "
            f"LOCAL_ONLY mode allows only {sorted(LOCAL_ENDPOINT_HOSTS)}."
        )


def local_boto3_client(
    service_name: str,
    settings: Settings | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Create a boto3 client, refusing any endpoint that is not a local emulator.

    This is the only place in the codebase that constructs AWS clients.
    `client_factory` exists so tests can assert the guard without boto3.
    """
    cfg = Settings.from_env() if settings is None else settings
    assert_local_endpoint(cfg.aws_endpoint_url, local_only=cfg.local_only)

    if client_factory is None:  # pragma: no cover - exercised in integration tests
        import boto3

        client_factory = boto3.client

    return client_factory(
        service_name,
        endpoint_url=cfg.aws_endpoint_url,
        region_name=cfg.aws_region,
    )
