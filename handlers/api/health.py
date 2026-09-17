"""Health endpoint. A composition root, so it is deliberately thin.

It reports which tables the function was configured with, because the most common
deployment fault is a function wired to the wrong stage's resources, and that is invisible
until something writes to the wrong place.
"""

from __future__ import annotations

import json
import os
from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    body = {
        "status": "ok",
        "service": "hallmark",
        "stage": os.environ.get("STAGE", "unknown"),
        "tenant": os.environ.get("TENANT_ID", "unknown"),
        "wired": {
            "values": bool(os.environ.get("VALUES_TABLE")),
            "lineage": bool(os.environ.get("LINEAGE_TABLE")),
            "decisions": bool(os.environ.get("DECISIONS_TABLE")),
            "vendors": bool(os.environ.get("VENDOR_TABLE")),
            "ledger": bool(os.environ.get("LEDGER_TABLE")),
            "bus": bool(os.environ.get("EVENT_BUS")),
        },
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
