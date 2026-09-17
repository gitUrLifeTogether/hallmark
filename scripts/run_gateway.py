"""Run the realtime gateway on the host.

It lives outside the deployed stack because the managed WebSocket API is not available on
the local emulator. Everything else about it is production-shaped: it drains the same queue
the deployed rule feeds, and forwards to browsers without touching the content.

Usage:  uv run python scripts/run_gateway.py
"""

from __future__ import annotations

import os
import sys

from hallmark.adapters.realtime.gateway import create_app
from hallmark.config import Settings, local_boto3_client

DEFAULT_PORT = 8787


def main() -> int:
    settings = Settings.from_env()
    queue_url = os.environ.get("CONSOLE_EVENTS_QUEUE")

    if not queue_url:
        print(
            'CONSOLE_EVENTS_QUEUE is not set.\nRun:  eval "$(uv run python scripts/stack_env.py)"',
            file=sys.stderr,
        )
        return 1

    import uvicorn

    sqs = local_boto3_client("sqs", settings)
    app = create_app(sqs, queue_url)

    port = int(os.environ.get("GATEWAY_PORT", DEFAULT_PORT))
    print(f"gateway on http://127.0.0.1:{port}  draining {queue_url}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
