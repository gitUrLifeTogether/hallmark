"""Contract tests: the DynamoDB adapters must behave like the in-memory ones.

The whole security kernel was tested against in-memory adapters. That is only sound if the
real adapters honour the same contract, so these run the same expectations against the
deployed stack. They are opt-in (`-m localstack`) because they need it running.

The cases that matter most are the ones where a difference would be silent: a value coming
back with its provenance altered, an integer amount returning as a float, or duplicate
detection missing a match because of key construction.
"""

from __future__ import annotations

import os
import uuid

import pytest

from hallmark.adapters.dynamodb.repositories import (
    DynamoLedgerRepository,
    DynamoVendorRepository,
)
from hallmark.adapters.dynamodb.stores import (
    DynamoDecisionStore,
    DynamoLineageStore,
    DynamoValueStore,
)
from hallmark.config import Settings
from hallmark.domain.labels import Confidentiality, Source, ValueType
from hallmark.domain.lineage import EdgeKind, LineageEdge
from hallmark.domain.values import Labeled
from hallmark.ports.repositories import LedgerEntry, Vendor
from hallmark.ports.stores import DecisionRecord

pytestmark = pytest.mark.localstack

TENANT = "kestrel"


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings.from_env(
        {
            "AWS_ENDPOINT_URL": os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
            "AWS_DEFAULT_REGION": "ap-south-1",
            "TENANT_ID": TENANT,
        }
    )


@pytest.fixture
def run_id() -> str:
    return f"run-{uuid.uuid4().hex[:10]}"


def test_a_labeled_value_round_trips_with_its_provenance_intact(
    settings: Settings, run_id: str
) -> None:
    """The one thing that must never be lost in storage."""
    store = DynamoValueStore(os.environ["VALUES_TABLE"], TENANT, settings)
    original = Labeled(
        handle="h_contract_1",
        value="889900771234",
        vtype=ValueType.ACCOUNT_NUMBER,
        sources=frozenset({Source.EXTERNAL_EMAIL, Source.MODEL_READER}),
        confidentiality=Confidentiality.CONFIDENTIAL,
        run_id=run_id,
        op="reader_extract",
        parents=("h_body",),
        declassified=True,
        display="XXXXXXXX1234",
        created_at="2026-09-17T00:00:00Z",
    )
    store.put(original)
    loaded = store.get(run_id, "h_contract_1")

    assert loaded is not None
    assert loaded.sources == original.sources
    assert loaded.trusted is False
    assert loaded.confidentiality is Confidentiality.CONFIDENTIAL
    assert loaded.parents == ("h_body",)
    assert loaded.declassified is True
    assert loaded.display == "XXXXXXXX1234"


def test_an_integer_amount_survives_as_an_integer(settings: Settings, run_id: str) -> None:
    """Money is integer paise. A float round-trip would be a silent rounding bug."""
    store = DynamoValueStore(os.environ["VALUES_TABLE"], TENANT, settings)
    store.put(
        Labeled(
            handle="h_amount",
            value=46_200_000,
            vtype=ValueType.MONEY_PAISE,
            sources=frozenset({Source.EXTERNAL_EMAIL}),
            confidentiality=Confidentiality.INTERNAL,
            run_id=run_id,
        )
    )
    loaded = store.get(run_id, "h_amount")

    assert loaded is not None
    assert loaded.value == 46_200_000
    assert isinstance(loaded.value, int)


def test_a_missing_handle_returns_none_rather_than_raising(settings: Settings, run_id: str) -> None:
    store = DynamoValueStore(os.environ["VALUES_TABLE"], TENANT, settings)
    assert store.get(run_id, "h_does_not_exist") is None


def test_runs_do_not_see_each_others_values(settings: Settings) -> None:
    """Partitioning by run is what keeps a handle meaningful only inside its run."""
    store = DynamoValueStore(os.environ["VALUES_TABLE"], TENANT, settings)
    first, second = f"run-{uuid.uuid4().hex[:8]}", f"run-{uuid.uuid4().hex[:8]}"

    store.put(
        Labeled(
            handle="h_shared",
            value="only in the first run",
            vtype=ValueType.FREE_TEXT,
            sources=frozenset({Source.COMPANY_DB}),
            confidentiality=Confidentiality.INTERNAL,
            run_id=first,
        )
    )

    assert store.get(first, "h_shared") is not None
    assert store.get(second, "h_shared") is None


def test_lineage_edges_come_back_for_their_run(settings: Settings, run_id: str) -> None:
    store = DynamoLineageStore(os.environ["LINEAGE_TABLE"], TENANT, settings)
    store.add_edge(
        LineageEdge("e1", run_id, "h_email", "h_account", EdgeKind.DERIVE, "reader_extract")
    )
    store.add_edge(LineageEdge("e2", run_id, "h_account", "dec_1", EdgeKind.ARG, "account"))

    edges = store.edges_for_run(run_id)
    assert len(edges) == 2
    assert {e.kind for e in edges} == {EdgeKind.DERIVE, EdgeKind.ARG}


def test_a_decision_round_trips_with_its_policies(settings: Settings, run_id: str) -> None:
    store = DynamoDecisionStore(os.environ["DECISIONS_TABLE"], TENANT, settings)
    store.add(
        DecisionRecord(
            decision_id="dec_1",
            run_id=run_id,
            tool="pay_vendor",
            args_handles={"account": "h_acc", "amount": "h_amt"},
            facts={"accountMatchesVendorMaster": False, "amountPaise": 46_200_000},
            allow=False,
            outcome="DENIED",
            determining_policies=("pay-account-must-be-master",),
            reason_code="ACCOUNT_NOT_FROM_VENDOR_MASTER",
            latency_ms=12,
            created_at="2026-09-17T00:00:00Z",
        )
    )
    loaded = store.for_run(run_id)

    assert len(loaded) == 1
    assert loaded[0].determining_policies == ("pay-account-must-be-master",)
    assert loaded[0].facts["accountMatchesVendorMaster"] is False
    assert loaded[0].facts["amountPaise"] == 46_200_000


def test_the_seeded_vendor_master_is_readable_by_gstin(settings: Settings) -> None:
    """The lookup a payment depends on."""
    repository = DynamoVendorRepository(os.environ["VENDOR_TABLE"], TENANT, settings)
    vendor = repository.by_gstin("27FGHIJ5678K1Z3")

    assert vendor is not None
    assert vendor.vendor_id == "v-suryodaya"
    assert vendor.account_number == "911020033456"
    assert repository.by_gstin("27fghij5678k1z3") is not None, "lookup must ignore case"


def test_all_vendors_returns_one_row_per_vendor_not_one_per_version(
    settings: Settings,
) -> None:
    """Versioning must not make a vendor appear several times in contact checks."""
    repository = DynamoVendorRepository(os.environ["VENDOR_TABLE"], TENANT, settings)
    vendors = repository.all_vendors()
    ids = [v.vendor_id for v in vendors]

    assert len(ids) == len(set(ids)), f"duplicate vendors returned: {ids}"
    assert len(vendors) >= 6


def test_a_bank_change_writes_a_new_version_and_keeps_the_old_one(
    settings: Settings,
) -> None:
    """History has to survive a legitimate change of bank."""
    repository = DynamoVendorRepository(os.environ["VENDOR_TABLE"], TENANT, settings)
    vendor_id = f"v-contract-{uuid.uuid4().hex[:6]}"

    original = Vendor(
        vendor_id=vendor_id,
        legal_name="Contract Test Supplies",
        gstin="27ZZZZZ9999Z1Z9",
        domain="contract.example",
        account_number="111122223333",
        ifsc="HDFC0009999",
        version=1,
    )
    repository.put(original)
    repository.put(Vendor(**{**original.__dict__, "account_number": "444455556666", "version": 2}))

    current = repository.by_id(vendor_id)
    assert current is not None
    assert current.account_number == "444455556666"
    assert current.version == 2


def test_duplicate_detection_finds_a_recorded_invoice(settings: Settings) -> None:
    ledger = DynamoLedgerRepository(os.environ["LEDGER_TABLE"], TENANT, settings)
    invoice = f"INV-CONTRACT-{uuid.uuid4().hex[:6].upper()}"

    assert ledger.has_invoice("v-northwind", invoice) is False

    ledger.record(
        LedgerEntry(
            txn_id=f"txn-{uuid.uuid4().hex[:8]}",
            run_id="run-contract",
            vendor_id="v-northwind",
            invoice_number=invoice,
            amount_paise=4_250_000,
            account_masked="XXXXXXXX7821",
        )
    )

    assert ledger.has_invoice("v-northwind", invoice) is True
    assert ledger.has_invoice("v-northwind", invoice.lower()) is True, "must ignore case"
    assert ledger.has_invoice("v-suryodaya", invoice) is False, "must be scoped to a vendor"
