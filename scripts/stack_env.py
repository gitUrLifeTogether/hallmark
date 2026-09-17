"""Print the deployed stack's resource names as shell exports.

Tests and the seed script read table names from the environment rather than guessing them,
so that pointing at the wrong stage is impossible rather than merely unlikely. This reads
the names back from the stack that actually exists.

Usage:  eval "$(uv run python scripts/stack_env.py)"
"""

from __future__ import annotations

import sys

from hallmark.config import Settings, local_boto3_client

STACK_NAME = "hallmark"

#: Logical resource id -> environment variable the code expects.
EXPORTS = {
    "ValuesTable": "VALUES_TABLE",
    "LineageTable": "LINEAGE_TABLE",
    "DecisionsTable": "DECISIONS_TABLE",
    "RunsTable": "RUNS_TABLE",
    "VendorTable": "VENDOR_TABLE",
    "LedgerTable": "LEDGER_TABLE",
    "ApprovalsTable": "APPROVALS_TABLE",
    "ArtifactsBucket": "ARTIFACTS_BUCKET",
    "ConsoleEventsQueue": "CONSOLE_EVENTS_QUEUE",
    "HallmarkBus": "EVENT_BUS",
}


def main() -> int:
    settings = Settings.from_env()
    client = local_boto3_client("cloudformation", settings)

    try:
        resources = client.describe_stack_resources(StackName=STACK_NAME)["StackResources"]
    except Exception:
        print(f"# stack '{STACK_NAME}' is not deployed; run `make deploy-local`", file=sys.stderr)
        return 1

    physical = {r["LogicalResourceId"]: r["PhysicalResourceId"] for r in resources}
    for logical, variable in EXPORTS.items():
        if logical in physical:
            print(f"export {variable}={physical[logical]}")

    outputs = client.describe_stacks(StackName=STACK_NAME)["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] == "ApiUrl":
            print(f"export HALLMARK_API_BASE={output['OutputValue']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
