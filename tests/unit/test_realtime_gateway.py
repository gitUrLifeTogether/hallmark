"""The gateway forwards events and never enriches them."""

from __future__ import annotations

import json
from typing import Any

import pytest

from hallmark.adapters.realtime.gateway import EventGateway

QUEUE = "http://localhost:4566/000000000000/console-events"


def envelope(run_id: str, detail_type: str = "PolicyEvaluated", **payload: Any) -> dict[str, Any]:
    return {
        "Body": json.dumps(
            {
                "detail-type": detail_type,
                "detail": {"runId": run_id, "at": "2026-09-17T00:00:00Z", "payload": payload},
            }
        ),
        "ReceiptHandle": f"rh-{run_id}-{detail_type}",
    }


class FakeSqs:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self._batches = batches
        self.deleted: list[str] = []

    def receive_message(self, **_: Any) -> dict[str, Any]:
        return {"Messages": self._batches.pop(0)} if self._batches else {}

    def delete_message(self, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)


class FakeSocket:
    """Stands in for a browser socket.

    Deliberately unhashable, like the real `WebSocket`, which extends a Mapping and so
    defines equality without a hash. A hashable double let a version of this gateway pass
    every test while closing real connections the moment they were accepted.
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class BrokenSocket:
    __hash__ = None  # type: ignore[assignment]

    async def send_text(self, text: str) -> None:
        raise ConnectionResetError("browser went away")


@pytest.mark.asyncio
async def test_an_event_reaches_a_subscriber() -> None:
    sqs = FakeSqs([[envelope("run-1", reasonCode="ACCOUNT_NOT_FROM_VENDOR_MASTER")]])
    gateway = EventGateway(sqs, QUEUE)
    socket = FakeSocket()
    gateway.subscribers.add(socket, "run-1")

    assert await gateway.poll_once() == 1
    assert socket.sent[0]["type"] == "PolicyEvaluated"
    assert socket.sent[0]["payload"]["reasonCode"] == "ACCOUNT_NOT_FROM_VENDOR_MASTER"


@pytest.mark.asyncio
async def test_a_subscriber_only_sees_the_run_it_asked_for() -> None:
    sqs = FakeSqs([[envelope("run-1"), envelope("run-2")]])
    gateway = EventGateway(sqs, QUEUE)
    first, second, everything = FakeSocket(), FakeSocket(), FakeSocket()
    gateway.subscribers.add(first, "run-1")
    gateway.subscribers.add(second, "run-2")
    gateway.subscribers.add(everything, None)

    await gateway.poll_once()

    assert [e["runId"] for e in first.sent] == ["run-1"]
    assert [e["runId"] for e in second.sent] == ["run-2"]
    assert len(everything.sent) == 2, "an unfiltered subscriber sees every run"


@pytest.mark.asyncio
async def test_the_gateway_forwards_without_enriching() -> None:
    """It must not resolve a handle to its value; that would undo the isolation."""
    sqs = FakeSqs([[envelope("run-1", account={"handle": "h_1", "trusted": False})]])
    gateway = EventGateway(sqs, QUEUE)
    socket = FakeSocket()
    gateway.subscribers.add(socket, "run-1")

    await gateway.poll_once()
    assert socket.sent[0]["payload"]["account"] == {"handle": "h_1", "trusted": False}


@pytest.mark.asyncio
async def test_an_unparseable_message_is_dropped_rather_than_blocking_the_queue() -> None:
    """Leaving it would stall every event behind it."""
    sqs = FakeSqs([[{"Body": "not json at all", "ReceiptHandle": "rh-bad"}]])
    gateway = EventGateway(sqs, QUEUE)

    assert await gateway.poll_once() == 0
    assert sqs.deleted == ["rh-bad"], "it must still be removed from the queue"


@pytest.mark.asyncio
async def test_a_closed_browser_does_not_stop_the_others_being_told() -> None:
    sqs = FakeSqs([[envelope("run-1")]])
    gateway = EventGateway(sqs, QUEUE)
    healthy = FakeSocket()
    gateway.subscribers.add(BrokenSocket(), "run-1")
    gateway.subscribers.add(healthy, "run-1")

    await gateway.poll_once()

    assert len(healthy.sent) == 1
    assert len(gateway.subscribers) == 1, "the dead socket is dropped"


@pytest.mark.asyncio
async def test_every_message_is_deleted_after_handling() -> None:
    sqs = FakeSqs([[envelope("run-1"), envelope("run-1", detail_type="ActionExecuted")]])
    gateway = EventGateway(sqs, QUEUE)

    await gateway.poll_once()
    assert len(sqs.deleted) == 2


@pytest.mark.asyncio
async def test_an_empty_queue_is_not_an_error() -> None:
    gateway = EventGateway(FakeSqs([]), QUEUE)
    assert await gateway.poll_once() == 0


async def test_an_unhashable_socket_can_subscribe() -> None:
    """The real WebSocket is a Mapping and cannot be a dict key.

    This is the exact fault that made the live gateway reject every connection with a 403
    while the unit tests were green, because the double was hashable and the real object
    is not.
    """
    gateway = EventGateway(FakeSqs([]), QUEUE)
    socket = FakeSocket()

    with pytest.raises(TypeError):
        {socket: "proves the double is unhashable"}  # noqa: B018

    gateway.subscribers.add(socket, "run-1")
    assert gateway.subscribers.interested_in("run-1") == [socket]

    gateway.subscribers.remove(socket)
    assert len(gateway.subscribers) == 0
