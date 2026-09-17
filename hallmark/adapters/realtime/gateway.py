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
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

# Imported at module scope on purpose. This module uses postponed annotation evaluation,
# so a handler's annotations are strings that the framework resolves against the module's
# globals. Importing WebSocket inside the factory left "WebSocket" unresolvable, and the
# framework silently fell back to treating the parameter as a required query string --
# every handshake was then rejected with a bare 403 and the handler never ran.
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

POLL_WAIT_SECONDS = 10
"""Long-poll duration. Long enough to be cheap, short enough to shut down promptly."""

MAX_MESSAGES_PER_POLL = 10


@dataclass
class Subscribers:
    """Connected browsers, optionally filtered to one run.

    Held as a list of pairs rather than a dict keyed by socket. A Starlette `WebSocket`
    extends `HTTPConnection`, which is a `Mapping`, so it defines equality without a hash
    and cannot be a dict key: using one closes the connection the instant it is accepted.
    """

    entries: list[tuple[Any, str | None]] = field(default_factory=list)

    def add(self, socket: Any, run_id: str | None = None) -> None:
        self.entries.append((socket, run_id))

    def remove(self, socket: Any) -> None:
        # Identity, not equality: two sockets could compare equal as mappings.
        self.entries = [entry for entry in self.entries if entry[0] is not socket]

    def interested_in(self, run_id: str) -> list[Any]:
        return [socket for socket, wanted in self.entries if wanted in (None, run_id)]

    def __len__(self) -> int:
        return len(self.entries)


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
    async def events(socket: WebSocket) -> None:
        # Read the filter straight off the request rather than declaring it as a typed
        # parameter: the framework's dependency resolution rejects the handshake outright
        # on a websocket route, and a 403 with no body is a miserable thing to debug.
        run_id = socket.query_params.get("runId") or None

        await socket.accept()
        gateway.subscribers.add(socket, run_id)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            gateway.subscribers.remove(socket)

    return app
