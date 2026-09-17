"""The LOCAL_ONLY guard must make it impossible to reach real AWS."""

from typing import Any

import pytest

from hallmark.config import (
    Settings,
    assert_local_endpoint,
    is_local_endpoint,
    local_boto3_client,
)
from hallmark.domain.errors import ConfigurationError

LOCAL_URLS = [
    "http://localhost:4566",
    "http://127.0.0.1:4566",
    "http://localstack:4566",
    "http://host.docker.internal:4566",
    "https://localhost:4566",
    "http://LOCALHOST:4566",
]

REAL_AWS_URLS = [
    "https://dynamodb.ap-south-1.amazonaws.com",
    "https://bedrock-runtime.us-east-1.amazonaws.com",
    "https://verifiedpermissions.ap-south-1.amazonaws.com",
    "https://s3.amazonaws.com",
    "http://localhost.evil.com:4566",
    "http://notlocalhost:4566",
    "http://169.254.169.254",
]


@pytest.mark.parametrize("url", LOCAL_URLS)
def test_local_emulator_endpoints_are_accepted(url: str) -> None:
    assert is_local_endpoint(url)
    assert_local_endpoint(url)


@pytest.mark.parametrize("url", REAL_AWS_URLS)
def test_real_aws_endpoints_are_refused(url: str) -> None:
    assert not is_local_endpoint(url)
    with pytest.raises(ConfigurationError):
        assert_local_endpoint(url)


@pytest.mark.parametrize("url", [None, ""])
def test_missing_endpoint_is_refused_because_boto3_would_use_real_aws(url: str | None) -> None:
    with pytest.raises(ConfigurationError):
        assert_local_endpoint(url)


def test_guard_can_be_disabled_only_by_turning_local_only_off() -> None:
    assert_local_endpoint("https://dynamodb.ap-south-1.amazonaws.com", local_only=False)


def test_settings_default_to_local_only_even_with_an_empty_environment() -> None:
    settings = Settings.from_env({})
    assert settings.local_only is True
    assert settings.aws_endpoint_url is None


def test_client_factory_is_never_called_for_a_real_aws_endpoint() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def spy(service_name: str, **kwargs: Any) -> str:
        calls.append((service_name, kwargs))
        return "client"

    settings = Settings.from_env({"AWS_ENDPOINT_URL": "https://dynamodb.ap-south-1.amazonaws.com"})
    with pytest.raises(ConfigurationError):
        local_boto3_client("dynamodb", settings, client_factory=spy)

    assert calls == []


def test_client_is_created_against_the_local_endpoint() -> None:
    captured: dict[str, Any] = {}

    def spy(service_name: str, **kwargs: Any) -> str:
        captured.update({"service": service_name, **kwargs})
        return "client"

    settings = Settings.from_env(
        {"AWS_ENDPOINT_URL": "http://localhost:4566", "AWS_DEFAULT_REGION": "ap-south-1"}
    )
    assert local_boto3_client("dynamodb", settings, client_factory=spy) == "client"
    assert captured["service"] == "dynamodb"
    assert captured["endpoint_url"] == "http://localhost:4566"
    assert captured["region_name"] == "ap-south-1"
