"""The user's confirmed scope for a run.

The mandate is the one part of an authorization request that never comes from the
planner. It is drafted from the user's words, confirmed by the user in the console, and
read back from storage at decision time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from hallmark.domain.errors import ValidationError

PAY_VENDOR: Final = "pay_vendor"
SEND_EMAIL: Final = "send_email"


@dataclass(frozen=True)
class Mandate:
    """What the agent is allowed to do, and up to what amounts.

    `auto_approve_limit_paise` is where a human gets involved; `max_amount_paise` is a
    hard ceiling that a human cannot lift from inside a run.
    """

    allowed_actions: frozenset[str]
    max_amount_paise: int
    auto_approve_limit_paise: int

    def __post_init__(self) -> None:
        if self.max_amount_paise <= 0:
            raise ValidationError("mandate cap must be positive")
        if self.auto_approve_limit_paise < 0:
            raise ValidationError("auto-approve limit cannot be negative")
        if self.auto_approve_limit_paise > self.max_amount_paise:
            raise ValidationError("auto-approve limit cannot exceed the mandate cap")

    def permits(self, action: str) -> bool:
        return action in self.allowed_actions

    def to_cedar_context(self) -> dict[str, object]:
        return {
            "allowedActions": sorted(self.allowed_actions),
            "maxAmountPaise": self.max_amount_paise,
            "autoApproveLimitPaise": self.auto_approve_limit_paise,
        }
