"""The episode deadline.

A call budget bounds how much a confused model does; it does not bound how long it takes.
One measured episode spent 3311 seconds inside a legitimate number of calls, so both limits
are needed and they fail for different reasons.
"""

from __future__ import annotations

import time

import pytest

from hallmark.application.planner import EpisodeFinished, _stop_if_spent
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


def test_an_exhausted_budget_stops_the_episode_rather_than_refusing_forever() -> None:
    """Refusing the work is not the same as stopping it.

    A budget that only made each further call a no-op left the agent loop running, and a
    model that never says DONE kept spending inferences until the deadline: ten tool calls
    against a budget of eight, every one of them refused.
    """
    tools = build_tools_for_test()
    tools.start_episode(2)

    _stop_if_spent(tools)  # nothing spent yet
    tools._spend_call("read_email")
    tools._spend_call("read_email")

    with pytest.raises(EpisodeFinished):
        _stop_if_spent(tools)


def test_a_passed_deadline_also_stops_the_episode() -> None:
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=0.05)
    time.sleep(0.1)

    with pytest.raises(EpisodeFinished):
        _stop_if_spent(tools)


def test_the_deadline_comes_forward_once_a_payment_is_decided() -> None:
    """The episode exists to reach a verdict, so a reached verdict should end it soon.

    One run made nineteen tool calls: the real work was done by the tenth and the rest was
    a small model failing to stop. A call budget never catches that, because refusing a
    call is not the same as ending an episode.
    """
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=3600)
    assert tools.payment_decided is False

    tools._settle()

    assert tools.payment_decided is True
    assert tools.deadline is not None
    # Far less than the hour it started with, and not yet expired.
    assert tools.out_of_time() is False
    assert tools.deadline - time.monotonic() < 120


def test_settling_never_extends_a_shorter_deadline() -> None:
    """Wrap-up is a ceiling, not a grant of extra time."""
    tools = build_tools_for_test()
    tools.start_episode(8, deadline_seconds=5)
    before = tools.deadline

    tools._settle()

    assert before is not None and tools.deadline is not None
    assert tools.deadline <= before


def test_a_new_episode_forgets_that_a_payment_was_decided() -> None:
    tools = build_tools_for_test()
    tools.start_episode(8)
    tools._settle()

    tools.start_episode(8)

    assert tools.payment_decided is False
