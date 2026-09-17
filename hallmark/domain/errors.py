"""Typed error hierarchy.

Mapped to `reason_code` enums and HTTP status codes only at boundaries. Never leak
stack traces or untrusted text through these to the planner or to API clients.
"""


class HallmarkError(Exception):
    """Base class for every error Hallmark raises deliberately."""


class ValidationError(HallmarkError):
    """Input failed a structural or type check."""


class AuthenticationError(HallmarkError):
    """The caller could not be identified.

    Distinct from ValidationError so the boundary can answer 401 without inspecting an
    error message. Callers must not learn which part of a token failed; telling an
    attacker whether a signature or an expiry was wrong is free information.
    """


class ConfigurationError(HallmarkError):
    """The process is configured in a way that is unsafe or unusable.

    Raised by the LOCAL_ONLY guard when an AWS endpoint is not a local emulator.
    """


class EnforcementError(HallmarkError):
    """The PEP could not complete a decision. Always resolves to a denial."""


class PolicyDenied(HallmarkError):
    """Cedar denied the requested action."""


class NotFound(HallmarkError):
    """A referenced entity does not exist."""


class Conflict(HallmarkError):
    """A state transition was attempted from a state that does not allow it."""


class DependencyError(HallmarkError):
    """An external dependency failed, timed out, or returned an unusable response."""
