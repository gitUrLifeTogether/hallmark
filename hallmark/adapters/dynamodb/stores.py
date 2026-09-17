"""DynamoDB implementations of the storage ports.

Keys are tenant-prefixed from the start (`TENANT#<tenant>#RUN#<run>`). The demo uses one
tenant, but a key layout is the one decision that is painful to change once there is data,
so it is made correctly now rather than retrofitted.

Every client here comes from the guarded factory, so these adapters cannot be pointed at
real AWS even by accident.
"""

from __future__ import annotations

from typing import Any

from hallmark.config import Settings, local_boto3_client
from hallmark.domain.labels import Confidentiality, Source, ValueType
from hallmark.domain.lineage import EdgeKind, LineageEdge
from hallmark.domain.values import Labeled
from hallmark.ports.stores import DecisionRecord


def run_key(tenant_id: str, run_id: str) -> str:
    """The partition key for everything belonging to one run."""
    return f"TENANT#{tenant_id}#RUN#{run_id}"


def _to_attr(value: Any) -> dict[str, Any]:
    """Encode a Python value into a DynamoDB attribute.

    Numbers are stored as strings because DynamoDB's N type round-trips through float in
    some clients, and money here is integer paise that must never acquire a fraction.
    """
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, list):
        return {"L": [_to_attr(item) for item in value]}
    if isinstance(value, dict):
        return {"M": {k: _to_attr(v) for k, v in value.items()}}
    if value is None:
        return {"NULL": True}
    return {"S": str(value)}


def _from_attr(attr: dict[str, Any]) -> Any:
    if "BOOL" in attr:
        return bool(attr["BOOL"])
    if "N" in attr:
        return int(attr["N"])
    if "L" in attr:
        return [_from_attr(item) for item in attr["L"]]
    if "M" in attr:
        return {k: _from_attr(v) for k, v in attr["M"].items()}
    if "NULL" in attr:
        return None
    if "SS" in attr:
        return list(attr["SS"])
    return str(attr["S"])


class DynamoValueStore:
    """Labeled values, keyed by run and handle."""

    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def put(self, value: Labeled[Any]) -> None:
        item: dict[str, Any] = {
            "pk": {"S": run_key(self._tenant, value.run_id)},
            "sk": {"S": f"VALUE#{value.handle}"},
            "handle": {"S": value.handle},
            "vtype": {"S": str(value.vtype)},
            "value": _to_attr(value.value),
            "sources": {"SS": sorted(str(s) for s in value.sources)},
            "confidentiality": {"S": str(value.confidentiality)},
            "op": {"S": value.op},
            "declassified": {"BOOL": value.declassified},
            "runId": {"S": value.run_id},
            "createdAt": {"S": value.created_at},
        }
        if value.parents:
            item["parents"] = {"L": [{"S": p} for p in value.parents]}
        if value.display is not None:
            item["display"] = {"S": value.display}

        self._client.put_item(TableName=self._table, Item=item)

    def get(self, run_id: str, handle: str) -> Labeled[Any] | None:
        response = self._client.get_item(
            TableName=self._table,
            Key={
                "pk": {"S": run_key(self._tenant, run_id)},
                "sk": {"S": f"VALUE#{handle}"},
            },
        )
        item = response.get("Item")
        if not item:
            return None

        return Labeled(
            handle=item["handle"]["S"],
            value=_from_attr(item["value"]),
            vtype=ValueType(item["vtype"]["S"]),
            sources=frozenset(Source(s) for s in item["sources"]["SS"]),
            confidentiality=Confidentiality(item["confidentiality"]["S"]),
            run_id=item["runId"]["S"],
            op=item["op"]["S"],
            parents=tuple(p["S"] for p in item.get("parents", {}).get("L", [])),
            declassified=bool(item["declassified"]["BOOL"]),
            display=item.get("display", {}).get("S"),
            created_at=item.get("createdAt", {}).get("S", ""),
        )


class DynamoLineageStore:
    """Provenance edges. Queried forwards by run, and backwards through the index."""

    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def add_edge(self, edge: LineageEdge) -> None:
        self._client.put_item(
            TableName=self._table,
            Item={
                "pk": {"S": run_key(self._tenant, edge.run_id)},
                "sk": {"S": f"EDGE#{edge.edge_id}"},
                "edgeId": {"S": edge.edge_id},
                "runId": {"S": edge.run_id},
                "sourceHandle": {"S": edge.source_handle},
                "targetHandle": {"S": edge.target_handle},
                "kind": {"S": str(edge.kind)},
                "label": {"S": edge.label},
            },
        )

    def edges_for_run(self, run_id: str) -> list[LineageEdge]:
        response = self._client.query(
            TableName=self._table,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": run_key(self._tenant, run_id)},
                ":prefix": {"S": "EDGE#"},
            },
        )
        return [
            LineageEdge(
                edge_id=item["edgeId"]["S"],
                run_id=item["runId"]["S"],
                source_handle=item["sourceHandle"]["S"],
                target_handle=item["targetHandle"]["S"],
                kind=EdgeKind(item["kind"]["S"]),
                label=item.get("label", {}).get("S", ""),
            )
            for item in response.get("Items", [])
        ]


class DynamoDecisionStore:
    """Enforcement decisions, kept for the audit trail and the console."""

    def __init__(self, table_name: str, tenant_id: str, settings: Settings | None = None) -> None:
        self._table = table_name
        self._tenant = tenant_id
        self._client = local_boto3_client("dynamodb", settings)

    def add(self, record: DecisionRecord) -> None:
        self._client.put_item(
            TableName=self._table,
            Item={
                "pk": {"S": run_key(self._tenant, record.run_id)},
                "sk": {"S": f"DECISION#{record.decision_id}"},
                "decisionId": {"S": record.decision_id},
                "runId": {"S": record.run_id},
                "tool": {"S": record.tool},
                "argsHandles": _to_attr(record.args_handles),
                "facts": _to_attr(record.facts),
                "allow": {"BOOL": record.allow},
                "outcome": {"S": record.outcome},
                "determiningPolicies": _to_attr(list(record.determining_policies)),
                "reasonCode": {"S": record.reason_code},
                "latencyMs": {"N": str(record.latency_ms)},
                "createdAt": {"S": record.created_at},
            },
        )

    def for_run(self, run_id: str) -> list[DecisionRecord]:
        response = self._client.query(
            TableName=self._table,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": run_key(self._tenant, run_id)},
                ":prefix": {"S": "DECISION#"},
            },
        )
        return [
            DecisionRecord(
                decision_id=item["decisionId"]["S"],
                run_id=item["runId"]["S"],
                tool=item["tool"]["S"],
                args_handles=_from_attr(item["argsHandles"]),
                facts=_from_attr(item["facts"]),
                allow=bool(item["allow"]["BOOL"]),
                outcome=item["outcome"]["S"],
                determining_policies=tuple(_from_attr(item["determiningPolicies"])),
                reason_code=item["reasonCode"]["S"],
                latency_ms=int(item["latencyMs"]["N"]),
                created_at=item.get("createdAt", {}).get("S", ""),
            )
            for item in response.get("Items", [])
        ]
