"""Spike check 1b: prove `cedarpy` evaluates policies inside a Lambda container,
and check 3: prove the same function can write to DynamoDB.

Throwaway. Not part of the product; the real PEP lives in hallmark/application/pep.py.
"""

import json
import os
from typing import Any

import boto3
import cedarpy

# The two policies that carry Hallmark's core guarantee.
POLICIES = """
@id("pay-permit-within-mandate")
permit(principal, action == Action::"pay_vendor", resource)
when { context.amountPaise <= context.maxAmountPaise };

@id("pay-account-must-be-master")
forbid(principal, action == Action::"pay_vendor", resource)
unless { context.account.trusted && context.accountMatchesVendorMaster };
"""


def _decide(amount: int, trusted: bool, matches: bool) -> str:
    request = {
        "principal": 'Agent::"run-spike"',
        "action": 'Action::"pay_vendor"',
        "resource": 'Vendor::"v-suryodaya"',
        "context": {
            "amountPaise": amount,
            "maxAmountPaise": 500000,
            "accountMatchesVendorMaster": matches,
            "account": {"trusted": trusted},
        },
    }
    return str(cedarpy.is_authorized(request, POLICIES, []).decision)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    legit = _decide(400000, trusted=True, matches=True)
    bec = _decide(462000, trusted=False, matches=False)

    result = {
        "cedar_import": "ok",
        "legit_payment": legit,
        "bec_email_derived_account": bec,
        # The whole point: the BEC case must be denied.
        "guarantee_holds": "Allow" in legit and "Deny" in bec,
    }

    table = os.environ.get("SPIKE_TABLE")
    if table:
        boto3.client("dynamodb", endpoint_url=os.environ.get("AWS_ENDPOINT_URL")).put_item(
            TableName=table,
            Item={"pk": {"S": "spike#cedar-in-lambda"}, "result": {"S": json.dumps(result)}},
        )
        result["dynamodb_write"] = "ok"

    return {"statusCode": 200, "body": json.dumps(result)}
