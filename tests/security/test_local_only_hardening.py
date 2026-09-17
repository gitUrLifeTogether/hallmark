"""Hardening: attempts to get past the LOCAL_ONLY guard.

The guard's job is to make reaching real infrastructure impossible rather than merely
discouraged. The unit tests cover the obvious endpoints; these cover the ways a URL can be
made to *look* local while resolving somewhere else, which is how this class of check
usually fails.
"""

from __future__ import annotations

import pytest

from hallmark.config import assert_local_endpoint, is_local_endpoint, local_boto3_client
from hallmark.domain.errors import ConfigurationError

#: Each of these has a host that is not a local emulator, however it reads at a glance.
LOOKS_LOCAL_BUT_IS_NOT = [
    # A subdomain, not the host itself.
    "http://localhost.attacker.example:4566",
    "http://127.0.0.1.attacker.example",
    "http://localstack.attacker.example",
    # Credentials before an @ make the real host the part after it.
    "http://localhost@attacker.example",
    "http://localhost:pass@attacker.example/",
    # A prefix or suffix of an allowed name is not that name.
    "http://notlocalhost:4566",
    "http://localhosts:4566",
    "http://xlocalstack:4566",
    # Real endpoints.
    "https://dynamodb.ap-south-1.amazonaws.com",
    "https://sts.amazonaws.com",
    # The cloud metadata service, which is the classic target.
    "http://169.254.169.254/latest/meta-data/",
    "http://[fd00:ec2::254]/latest/meta-data/",
]

GENUINELY_LOCAL = [
    "http://localhost:4566",
    "http://127.0.0.1:4566",
    "http://localstack:4566",
    "http://host.docker.internal:4566",
    "https://localhost:4566",
    "http://LocalHost:4566",
]


@pytest.mark.parametrize("url", LOOKS_LOCAL_BUT_IS_NOT)
def test_a_url_that_only_looks_local_is_refused(url: str) -> None:
    assert not is_local_endpoint(url), f"{url} was accepted as local"
    with pytest.raises(ConfigurationError):
        assert_local_endpoint(url)


@pytest.mark.parametrize("url", GENUINELY_LOCAL)
def test_a_genuinely_local_endpoint_is_accepted(url: str) -> None:
    assert is_local_endpoint(url)
    assert_local_endpoint(url)


@pytest.mark.parametrize("url", [None, "", "   ", "not-a-url", "://missing-scheme"])
def test_an_unusable_endpoint_is_refused_rather_than_defaulted(url: str | None) -> None:
    """A missing endpoint means boto3 would reach the real service, so it must refuse."""
    with pytest.raises(ConfigurationError):
        assert_local_endpoint(url)


def test_the_client_factory_is_never_reached_for_a_non_local_endpoint() -> None:
    """The guard runs before anything is constructed, not after."""
    from hallmark.config import Settings

    attempts: list[str] = []

    def spy(service_name: str, **_: object) -> str:
        attempts.append(service_name)
        return "client"

    for url in LOOKS_LOCAL_BUT_IS_NOT:
        settings = Settings.from_env({"AWS_ENDPOINT_URL": url})
        with pytest.raises(ConfigurationError):
            local_boto3_client("dynamodb", settings, client_factory=spy)

    assert attempts == [], "a client was constructed for a non-local endpoint"


def test_a_typo_leaves_the_guard_on() -> None:
    """The asymmetry that matters: a guard must not fail open on a value it cannot read.

    Treating anything unrecognised as "off" means `LOCAL_ONLY=ture` silently disables the
    protection while everything still appears to work.
    """
    from hallmark.config import Settings

    for value in ["maybe", "ture", "yes-please", "1 ", "enabled", "TRUE"]:
        assert Settings.from_env({"LOCAL_ONLY": value}).local_only is True, value


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " off "])
def test_only_an_explicit_recognised_value_turns_the_guard_off(value: str) -> None:
    from hallmark.config import Settings

    assert Settings.from_env({"LOCAL_ONLY": value}).local_only is False


def test_the_guard_defaults_to_on_when_unset_or_blank() -> None:
    from hallmark.config import Settings

    assert Settings.from_env({}).local_only is True
    assert Settings.from_env({"LOCAL_ONLY": ""}).local_only is True
    assert Settings.from_env({"LOCAL_ONLY": "   "}).local_only is True
