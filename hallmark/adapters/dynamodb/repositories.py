"""DynamoDB implementations of the mock enterprise systems.

The vendor master is versioned: a bank change writes a new version rather than editing the
existing record, so the account a payment was checked against can always be recovered from
the audit trail even after the vendor legitimately changes banks.
"""

from __future__ import annotations

from typing import Any

from hallmark.config import Settings, local_boto3_client
from hallmark.ports.repositories import (
    EmailAttachment,
    InboxEmail,
    LedgerEntry,
    Vendor,
)

CURRENT_VERSION = 0
"""Sort key of the pointer row holding the live version of a vendor record."""


def _vendor_from_item(item: dict[str, Any]) -> Vendor:
    return Vendor(
        vendor_id=item["vendorId"]["S"],
        legal_name=item["legalName"]["S"],
        gstin=item["gstin"]["S"],
        domain=item["domain"]["S"],
        account_number=item["accountNumber"]["S"],
        ifsc=item["ifsc"]["S"],
        status=item.get("status", {}).get("S", "ACTIVE"),
        contact_emails=tuple(c["S"] for c in item.get("contactEmails", {}).get("L", [])),
        contact_phone=item.get("contactPhone", {}).get("S", ""),
        version=int(item.get("version", {}).get("N", "1")),
    )


class DynamoVendorRepository:
    """The vendor master. The only source of a payable bank account."""

    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def _pk(self, vendor_id: str) -> str:
        return f"TENANT#{self._tenant}#VENDOR#{vendor_id}"

    def put(self, vendor: Vendor) -> None:
        """Write a vendor version and point the current row at it."""
        attrs: dict[str, Any] = {
            "vendorId": {"S": vendor.vendor_id},
            "legalName": {"S": vendor.legal_name},
            "gstin": {"S": vendor.gstin},
            "domain": {"S": vendor.domain},
            "accountNumber": {"S": vendor.account_number},
            "ifsc": {"S": vendor.ifsc},
            "status": {"S": vendor.status},
            "contactEmails": {"L": [{"S": c} for c in vendor.contact_emails]},
            "contactPhone": {"S": vendor.contact_phone},
            "version": {"N": str(vendor.version)},
        }
        for sort_key in (vendor.version, CURRENT_VERSION):
            self._client.put_item(
                TableName=self._table,
                Item={
                    "pk": {"S": self._pk(vendor.vendor_id)},
                    "sk": {"N": str(sort_key)},
                    "gstin_lookup": {"S": vendor.gstin.upper()},
                    **attrs,
                },
            )

    def by_id(self, vendor_id: str) -> Vendor | None:
        response = self._client.get_item(
            TableName=self._table,
            Key={"pk": {"S": self._pk(vendor_id)}, "sk": {"N": str(CURRENT_VERSION)}},
        )
        item = response.get("Item")
        return _vendor_from_item(item) if item else None

    def by_gstin(self, gstin: str) -> Vendor | None:
        response = self._client.query(
            TableName=self._table,
            IndexName="gstin-index",
            KeyConditionExpression="gstin_lookup = :g",
            ExpressionAttributeValues={":g": {"S": gstin.strip().upper()}},
        )
        current = [i for i in response.get("Items", []) if int(i["sk"]["N"]) == CURRENT_VERSION]
        return _vendor_from_item(current[0]) if current else None

    def all_vendors(self) -> list[Vendor]:
        """Every current vendor.

        This is the one place a full read is acceptable: the vendor master is small and
        bounded, and outbound email checks need every known contact address.
        """
        vendors: list[Vendor] = []
        params: dict[str, Any] = {
            "TableName": self._table,
            "FilterExpression": "sk = :current",
            "ExpressionAttributeValues": {":current": {"N": str(CURRENT_VERSION)}},
        }

        while True:
            response = self._client.scan(**params)
            vendors.extend(_vendor_from_item(item) for item in response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return vendors
            params["ExclusiveStartKey"] = last_key


class DynamoLedgerRepository:
    """Payments made, and payments awaiting approval."""

    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def has_invoice(self, vendor_id: str, invoice_number: str) -> bool:
        """Whether this vendor and invoice number were already settled or are pending.

        Queried by an exact key rather than scanned, because duplicate detection runs on
        every payment and is the check an attacker would most like to see time out.
        """
        response = self._client.query(
            TableName=self._table,
            IndexName="invoice-index",
            KeyConditionExpression="invoice_lookup = :k",
            ExpressionAttributeValues={
                ":k": {"S": f"{self._tenant}#{vendor_id}#{invoice_number.strip().upper()}"}
            },
        )
        return any(
            item.get("status", {}).get("S") in {"SETTLED", "PENDING"}
            for item in response.get("Items", [])
        )

    def record(self, entry: LedgerEntry) -> None:
        self._client.put_item(
            TableName=self._table,
            Item={
                "pk": {"S": f"TENANT#{self._tenant}#TXN#{entry.txn_id}"},
                "txnId": {"S": entry.txn_id},
                "runId": {"S": entry.run_id},
                "vendorId": {"S": entry.vendor_id},
                "invoiceNumber": {"S": entry.invoice_number},
                "invoice_lookup": {
                    "S": f"{self._tenant}#{entry.vendor_id}#{entry.invoice_number.upper()}"
                },
                "amountPaise": {"N": str(entry.amount_paise)},
                "accountMasked": {"S": entry.account_masked},
                "status": {"S": entry.status},
            },
        )

    def entries(self) -> list[LedgerEntry]:
        response = self._client.scan(TableName=self._table)
        return [
            LedgerEntry(
                txn_id=item["txnId"]["S"],
                run_id=item["runId"]["S"],
                vendor_id=item["vendorId"]["S"],
                invoice_number=item["invoiceNumber"]["S"],
                amount_paise=int(item["amountPaise"]["N"]),
                account_masked=item["accountMasked"]["S"],
                status=item.get("status", {}).get("S", "SETTLED"),
            )
            for item in response.get("Items", [])
        ]


class S3InboxRepository:
    """Fixture inboxes stored as JSON in S3, one object per inbox."""

    def __init__(self, bucket: str, key: str, settings: Settings | None = None) -> None:
        self._bucket = bucket
        self._key = key
        self._client = local_boto3_client("s3", settings)
        self._cache: list[InboxEmail] | None = None

    def _load(self) -> list[InboxEmail]:
        if self._cache is not None:
            return self._cache

        import json

        body = self._client.get_object(Bucket=self._bucket, Key=self._key)["Body"].read()
        raw = json.loads(body)
        self._cache = [
            InboxEmail(
                email_id=e["email_id"],
                sender=e["sender"],
                sender_display_name=e.get("sender_display_name", ""),
                subject=e.get("subject", ""),
                body=e.get("body", ""),
                received_at=e.get("received_at", ""),
                dkim_pass=bool(e.get("dkim_pass", True)),
                hidden_text=e.get("hidden_text", ""),
                attachments=tuple(
                    EmailAttachment(
                        attachment_id=a["attachment_id"],
                        filename=a.get("filename", ""),
                        text=a.get("text", ""),
                        hidden_text=a.get("hidden_text", ""),
                    )
                    for a in e.get("attachments", [])
                ),
            )
            for e in raw
        ]
        return self._cache

    def list_emails(self) -> list[InboxEmail]:
        return list(self._load())

    def get(self, email_id: str) -> InboxEmail | None:
        return next((e for e in self._load() if e.email_id == email_id), None)
