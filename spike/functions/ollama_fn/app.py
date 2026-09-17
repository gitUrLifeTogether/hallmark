"""Spike check 2: prove a Lambda container can reach Ollama on the host.

Scope: the *network path* from a Lambda container to the model server only, not
output quality. Uses stdlib urllib so the zip stays tiny; packaging the Strands SDK into
the planner Lambda is a separate concern proven in M3.
"""

import json
import os
import urllib.request
from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    host = os.environ["OLLAMA_HOST"].rstrip("/")
    model = os.environ.get("READER_MODEL", "qwen3:1.7b")

    payload = json.dumps(
        {
            "model": model,
            "prompt": "Reply with the single word: reachable",
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 16},
        }
    ).encode()

    request = urllib.request.Request(
        f"{host}/api/generate", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=240) as response:  # noqa: S310
        body = json.loads(response.read())

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "network_path": "ok",
                "ollama_host": host,
                "model": body.get("model"),
                "response_text": (body.get("response") or "").strip()[:80],
            }
        ),
    }
