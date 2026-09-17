"""The realtime gateway: SQS on one side, browser WebSockets on the other.

This runs on the host rather than as a deployed function, because the managed WebSocket
API belongs to the same service family the local emulator does not provide. The production
shape would replace this file with an API Gateway WebSocket and a fan-out function; nothing
either side of it would change, which is why it lives behind its own small interface.

It forwards events and never enriches them. Everything arriving here has already been
reduced to handles, enums and provenance labels by the enforcement point, and a gateway
that "helpfully" resolved a handle to its value would undo that in one line.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

POLL_WAIT_SECONDS = 10
"""Long-poll duration. Long enough to be cheap, short enough to shut down promptly."""

MAX_MESSAGES_PER_POLL = 10


@dataclass
class Subscribers:
    """Connected browsers, optionally filtered to one run."""

    sockets: dict[Any, str | None] = field(default_factory=dict)

    def add(self, socket: Any, run_id: str | None = None) -> None:
        self.sockets[socket] = run_id

    def remove(self, socket: Any) -> None:
        self.sockets.pop(socket, None)

    def interested_in(self, run_id: str) -> list[Any]:
        return [s for s, wanted in self.sockets.items() if wanted in (None, run_id)]


class EventGateway:
    """Drains the queue and pushes each event to whoever is watching that run."""

    def __init__(self, sqs_client: Any, queue_url: str) -> None:
        self._sqs = sqs_client
        self._queue_url = queue_url
        self.subscribers = Subscribers()
        self.forwarded = 0
        self._running = False

    def _parse(self, body: str) -> dict[str, Any] | None:
        """Unwrap the event envelope, tolerating anything unexpected on the queue."""
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("discarding unparseable queue message")
            return None

        detail = envelope.get("detail")
        if not isinstance(detail, dict):
            return None

        return {
            "type": envelope.get("detail-type", "Unknown"),
            "runId": detail.get("runId", ""),
            "at": detail.get("at", ""),
            "payload": detail.get("payload", {}),
        }

    async def _deliver(self, event: dict[str, Any]) -> None:
        message = json.dumps(event)
        for socket in self.subscribers.interested_in(str(event.get("runId", ""))):
            try:
                await socket.send_text(message)
            except Exception:
                # A browser that closed mid-send must not stop the others being told.
                self.subscribers.remove(socket)

    async def poll_once(self) -> int:
        """Drain one batch. Returns how many events were forwarded."""
        response = await asyncio.to_thread(
            self._sqs.receive_message,
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=MAX_MESSAGES_PER_POLL,
            WaitTimeSeconds=POLL_WAIT_SECONDS,
        )

        delivered = 0
        for message in response.get("Messages", []):
            event = self._parse(message.get("Body", ""))
            if event is not None:
                await self._deliver(event)
                delivered += 1
                self.forwarded += 1

            # Delete regardless: an event that cannot be parsed will not parse next time
            # either, and leaving it would block the queue behind it forever.
            await asyncio.to_thread(
                self._sqs.delete_message,
                QueueUrl=self._queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )

        return delivered

    async def run_forever(self) -> None:
        """Poll until cancelled, surviving transient failures."""
        self._running = True
        while self._running:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("poll failed; retrying", exc_info=False)
                await asyncio.sleep(2)

    def stop(self) -> None:
        self._running = False


def create_app(sqs_client: Any, queue_url: str) -> Any:
    """Build the FastAPI application hosting the gateway."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, WebSocket, WebSocketDisconnect

    gateway = EventGateway(sqs_client, queue_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        task = asyncio.create_task(gateway.run_forever())
        yield
        gateway.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Hallmark realtime gateway", lifespan=lifespan)
    app.state.gateway = gateway

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "forwarded": gateway.forwarded}

    @app.websocket("/events")
    async def events(socket: WebSocket, runId: str | None = None) -> None:
        await socket.accept()
        gateway.subscribers.add(socket, runId)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            gateway.subscribers.remove(socket)

    return app
