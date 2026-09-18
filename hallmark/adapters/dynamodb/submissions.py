"""Submitted emails in DynamoDB, waiting for the run worker.

Shares the Runs table. A submission is a run that has not started yet, so giving it its own
table would mean two places to look for the same thing.
"""

from __future__ import annotations

import json
from typing import Any

from hallmark.application.submissions import Submission
from hallmark.config import Settings, local_boto3_client
from hallmark.domain.errors import NotFound


class DynamoSubmissionStore:
    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def _pk(self, run_id: str) -> str:
        return f"TENANT#{self._tenant}#RUN#{run_id}"

    def put(self, submission: Submission, status: str) -> None:
        self._client.put_item(
            TableName=self._table,
            Item={
                "pk": {"S": self._pk(submission.run_id)},
                "runId": {"S": submission.run_id},
                "sender": {"S": submission.sender},
                "subject": {"S": submission.subject},
                "body": {"S": submission.body},
                "attachmentText": {"S": submission.attachment_text},
                "status": {"S": status},
            },
        )

    def _item(self, run_id: str) -> dict[str, Any]:
        got = self._client.get_item(TableName=self._table, Key={"pk": {"S": self._pk(run_id)}})
        item: dict[str, Any] = got.get("Item", {})
        if not item:
            raise NotFound("no such run")
        return item

    def get(self, run_id: str) -> tuple[Submission, str]:
        item = self._item(run_id)
        plain = {k: v.get("S", "") for k, v in item.items() if "S" in v}
        return Submission.from_item(plain), plain.get("status", "QUEUED")

    def set_status(self, run_id: str, status: str, summary: dict[str, Any] | None = None) -> None:
        names = {"#s": "status"}
        values: dict[str, Any] = {":s": {"S": status}}
        expression = "SET #s = :s"
        if summary is not None:
            # Stored as one JSON string rather than a nested map: it is read back whole by
            # the console and never queried by field.
            names["#y"] = "summary"
            values[":y"] = {"S": json.dumps(summary)}
            expression += ", #y = :y"

        self._client.update_item(
            TableName=self._table,
            Key={"pk": {"S": self._pk(run_id)}},
            UpdateExpression=expression,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    def status_of(self, run_id: str) -> dict[str, Any]:
        item = self._item(run_id)
        raw_summary = item.get("summary", {}).get("S")
        return {
            "runId": run_id,
            "status": item.get("status", {}).get("S", "QUEUED"),
            "summary": json.loads(raw_summary) if raw_summary else None,
        }
