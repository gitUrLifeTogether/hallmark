"""Load the demo fixtures into the local stack.

Idempotent by construction: every write is a put of a known key, so running it twice
leaves the same state. That matters because the emulator is configured without
persistence, so this runs again after every restart.

Reads table names from the environment the deployed stack sets, so it cannot be pointed
at the wrong stage by accident.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from fixtures.hero import COMPANY, VENDORS, build_inbox
from hallmark.adapters.dynamodb.repositories import DynamoVendorRepository
from hallmark.config import Settings, local_boto3_client

HERO_INBOX_KEY = "inboxes/hero.json"


def seed_vendors(settings: Settings) -> int:
    """Write the vendor master. This is the only source of a payable account."""
    table = os.environ["VENDOR_TABLE"]
    repository = DynamoVendorRepository(table, settings.tenant_id, settings)
    for vendor in VENDORS:
        repository.put(vendor)
    return len(VENDORS)


def seed_inbox(settings: Settings) -> int:
    """Upload the hero inbox as a single JSON object."""
    bucket = os.environ["ARTIFACTS_BUCKET"]
    emails = build_inbox()
    payload = json.dumps([asdict(email) for email in emails], indent=2)

    client = local_boto3_client("s3", settings)
    client.put_object(
        Bucket=bucket,
        Key=HERO_INBOX_KEY,
        Body=payload.encode("utf-8"),
        ContentType="application/json",
    )
    return len(emails)


def seed_company(settings: Settings) -> None:
    """Store the operating company, which defines what counts as an internal address."""
    client = local_boto3_client("dynamodb", settings)
    client.put_item(
        TableName=os.environ["RUNS_TABLE"],
        Item={
            "pk": {"S": f"TENANT#{settings.tenant_id}#COMPANY"},
            "name": {"S": COMPANY.name},
            "domain": {"S": COMPANY.domain},
            "internalEmails": {"L": [{"S": e} for e in COMPANY.internal_emails]},
        },
    )


def main() -> int:
    settings = Settings.from_env()

    required = ["VENDOR_TABLE", "ARTIFACTS_BUCKET", "RUNS_TABLE"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"Missing environment: {', '.join(missing)}", file=sys.stderr)
        print("Run `make deploy-local` first, then source the stack outputs.", file=sys.stderr)
        return 1

    vendors = seed_vendors(settings)
    emails = seed_inbox(settings)
    seed_company(settings)

    print(f"seeded {vendors} vendors, {emails} emails, 1 company into stage {settings.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
