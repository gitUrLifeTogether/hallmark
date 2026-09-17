"""Spike check 4b: a second Lambda resumes the paused execution via SendTaskSuccess.

This is the approver's side of the real ApprovalWorkflow (CLAUDE.md §11.2).
"""

import json
import os
from typing import Any

import boto3


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    approval_id = event.get("approvalId", "spike-approval-1")
    endpoint = os.environ.get("AWS_ENDPOINT_URL")

    item = boto3.client("dynamodb", endpoint_url=endpoint).get_item(
        TableName=os.environ["SPIKE_TABLE"],
        Key={"pk": {"S": f"token#{approval_id}"}},
    )["Item"]

    boto3.client("stepfunctions", endpoint_url=endpoint).send_task_success(
        taskToken=item["taskToken"]["S"],
        output=json.dumps({"decision": "APPROVE", "approvalId": approval_id}),
    )
    return {"resumed": approval_id}
