"""EventBridge publisher, and a null one for tests.

Publishing never raises. A console that cannot be told about a decision is a degraded
console; a decision that fails because the console could not be told would be a far worse
outcome, so the failure is swallowed and counted rather than propagated.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hallmark.config import Settings, local_boto3_client
from hallmark.ports.events import DomainEvent

logger = logging.getLogger(__name__)

EVENT_SOURCE = "hallmark"


class EventBridgePublisher:
    """Sends events to the bus the console gateway drains."""

    def __init__(self, bus_name: str, settings: Settings | None = None) -> None:
        self._bus = bus_name
        self._client = local_boto3_client("events", settings)
        self.failures = 0

    def publish(self, event: DomainEvent) -> None:
        entry: dict[str, Any] = {
            "Source": EVENT_SOURCE,
            "DetailType": str(event.type),
            "EventBusName": self._bus,
            "Detail": json.dumps({"runId": event.run_id, "at": event.at, "payload": event.payload}),
        }
        try:
            self._client.put_events(Entries=[entry])
        except Exception:
            # Deliberately swallowed: see the module docstring.
            self.failures += 1
            logger.warning("event publish failed", extra={"eventType": str(event.type)})
