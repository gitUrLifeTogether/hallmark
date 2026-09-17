"""Spike check 4a: the Task state hands us a task token; park it and return nothing.

This mirrors the real ApprovalWorkflow (CLAUDE.md §11.2): the workflow pauses here until a
human decides, so the token must survive outside the execution.
"""

import os
from typing import Any

import boto3


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    token = event["taskToken"]
    approval_id = event.get("approvalId", "spike-approval-1")

    boto3.client("dynamodb", endpoint_url=os.environ.get("AWS_ENDPOINT_URL")).put_item(
        TableName=os.environ["SPIKE_TABLE"],
        Item={"pk": {"S": f"token#{approval_id}"}, "taskToken": {"S": token}},
    )
    return {"parked": approval_id}
