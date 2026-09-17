"""M0 placeholder handler: confirms the SAM stack deploys and serves traffic."""

from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return {"statusCode": 200, "body": '{"status": "ok", "service": "hallmark"}'}
