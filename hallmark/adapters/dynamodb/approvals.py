"""Approvals in DynamoDB, with a conditional write on the status change.

The conditional write is the whole point of this adapter. Two approvers clicking at the
same moment must not both succeed, because the second success would re-run enforcement and
could execute the payment twice. The condition makes the loser's write fail rather than
overwrite, and the service turns that into a clear conflict.
"""

from __future__ import annotations

from typing import Any

from hallmark.application.approvals import PendingAction
from hallmark.config import Settings, local_boto3_client
from hallmark.domain.statuses import ApprovalStatus


class DynamoApprovalStore:
    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def _pk(self, approval_id: str) -> str:
        return f"TENANT#{self._tenant}#APPROVAL#{approval_id}"

    def put(self, action: PendingAction) -> None:
        item: dict[str, Any] = {
            "pk": {"S": self._pk(action.approval_id)},
            "approvalId": {"S": action.approval_id},
            "runId": {"S": action.run_id},
            "decisionId": {"S": action.decision_id},
            "tool": {"S": action.tool},
            "amountPaise": {"N": str(action.amount_paise)},
            "requiredRole": {"S": action.required_role},
            "status": {"S": str(action.status)},
            "arguments": {"M": {k: {"S": v} for k, v in action.arguments.items()}},
        }
        if action.task_token:
            item["taskToken"] = {"S": action.task_token}
        if action.expires_at:
            item["expiresAt"] = {"S": action.expires_at}

        self._client.put_item(TableName=self._table, Item=item)

    def _to_action(self, item: dict[str, Any]) -> PendingAction:
        return PendingAction(
            approval_id=item["approvalId"]["S"],
            run_id=item["runId"]["S"],
            decision_id=item["decisionId"]["S"],
            tool=item["tool"]["S"],
            amount_paise=int(item["amountPaise"]["N"]),
            required_role=item["requiredRole"]["S"],
            status=ApprovalStatus(item["status"]["S"]),
            task_token=item.get("taskToken", {}).get("S"),
            decided_by=item.get("decidedBy", {}).get("S"),
            decided_at=item.get("decidedAt", {}).get("S"),
            expires_at=item.get("expiresAt", {}).get("S"),
            arguments={k: v["S"] for k, v in item.get("arguments", {}).get("M", {}).items()},
        )

    def get(self, approval_id: str) -> PendingAction | None:
        response = self._client.get_item(
            TableName=self._table, Key={"pk": {"S": self._pk(approval_id)}}
        )
        item = response.get("Item")
        return self._to_action(item) if item else None

    def pending(self) -> list[PendingAction]:
        response = self._client.scan(
            TableName=self._table,
            FilterExpression="#s = :pending AND begins_with(pk, :tenant)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":pending": {"S": str(ApprovalStatus.PENDING)},
                ":tenant": {"S": f"TENANT#{self._tenant}#APPROVAL#"},
            },
        )
        return [self._to_action(item) for item in response.get("Items", [])]

    def transition(
        self,
        approval_id: str,
        expected: ApprovalStatus,
        target: ApprovalStatus,
        by: str,
        at: str,
    ) -> bool:
        """Change the status only if it is still `expected`.

        Returns False when the condition fails, which means somebody else decided first.
        """
        try:
            self._client.update_item(
                TableName=self._table,
                Key={"pk": {"S": self._pk(approval_id)}},
                UpdateExpression="SET #s = :target, decidedBy = :by, decidedAt = :at",
                ConditionExpression="#s = :expected",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":target": {"S": str(target)},
                    ":expected": {"S": str(expected)},
                    ":by": {"S": by},
                    ":at": {"S": at},
                },
            )
            return True
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
