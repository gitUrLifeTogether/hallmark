"""The episode deadline.

A call budget bounds how much a confused model does; it does not bound how long it takes.
One measured episode spent 3311 seconds inside a legitimate number of calls, so both limits
are needed and they fail for different reasons.
"""

from __future__ import annotations

import time

from tests.unit.helpers import build_tools_for_test


def test_a_fresh_episode_has_time_left() -> None:
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=60)

    assert tools.out_of_time() is False


def test_an_episode_without_a_deadline_never_runs_out() -> None:
    """Tests and the scripted planner run without one, and must not start failing."""
    tools = build_tools_for_test()
    tools.start_episode(8)

    assert tools.out_of_time() is False


def test_time_runs_out_once_the_deadline_passes() -> None:
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=0.05)
    time.sleep(0.1)

    assert tools.out_of_time() is True


def test_a_tool_called_after_the_deadline_is_refused() -> None:
    """The refusal is what actually stops the loop; the flag alone would change nothing."""
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=0.05)
    time.sleep(0.1)

    assert tools._spend_call("read_email") is False


def test_the_budget_still_applies_inside_the_deadline() -> None:
    """The two limits are independent, and neither may mask the other."""
    tools = build_tools_for_test()
    tools.start_episode(2, deadline_seconds=60)

    assert tools._spend_call("read_email") is True
    assert tools._spend_call("read_email") is True
    assert tools._spend_call("read_email") is False


def test_starting_a_new_episode_resets_the_clock() -> None:
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=0.05)
    time.sleep(0.1)
    assert tools.out_of_time() is True

    tools.start_episode(8, deadline_seconds=60)

    assert tools.out_of_time() is False
