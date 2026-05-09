import os
from datetime import timedelta

os.environ["AUTO_INIT_DB"] = "false"
os.environ["JWT_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Loan, RefundLedger, ScanEvent
from app.seed import seed_demo_data
from app.time_utils import now_taipei
from app.views import create_sqlite_views


@pytest.fixture()
def context(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    create_sqlite_views(engine)

    db = TestingSessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()
    engine.dispose()


def login_headers(client: TestClient, username: str = "tea_owner") -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def create_qr_batch(client: TestClient, headers: dict[str, str], invoice: str = "INV-001", cup_count: int = 1) -> dict:
    response = client.post(
        "/merchant/qr-codes",
        headers=headers,
        json={"invoiceCode": invoice, "cupCount": cup_count},
    )
    assert response.status_code == 201
    return response.json()


def create_qr(client: TestClient, headers: dict[str, str], invoice: str = "INV-001") -> dict:
    return create_qr_batch(client, headers, invoice=invoice, cup_count=1)["items"][0]


def stats_range() -> dict[str, str]:
    now = now_taipei()
    return {
        "from": (now - timedelta(days=1)).isoformat(),
        "to": (now + timedelta(days=1)).isoformat(),
    }


def test_login_success_and_failure(context):
    client, _ = context

    success = client.post("/auth/login", json={"username": "tea_owner", "password": "password123"})
    assert success.status_code == 200
    assert success.json()["accessToken"]
    assert success.json()["store"]["code"] == "tea-shop"

    failure = client.post("/auth/login", json={"username": "tea_owner", "password": "bad"})
    assert failure.status_code == 401


def test_create_qr_code_uses_cup_count_and_deposit_amounts(context):
    client, _ = context
    headers = login_headers(client)

    batch = create_qr_batch(client, headers, invoice="CUP-001", cup_count=3)

    assert batch["invoiceCode"] == "CUP-001"
    assert batch["storeCode"] == "tea-shop"
    assert batch["cupCount"] == 3
    assert batch["startSequence"] == 1
    assert batch["endSequence"] == 3
    assert batch["totalDepositAmount"] == 60
    assert [item["invoiceSequence"] for item in batch["items"]] == [1, 2, 3]
    assert [item["qrValue"] for item in batch["items"]] == [
        "CUP-001|tea-shop|1",
        "CUP-001|tea-shop|2",
        "CUP-001|tea-shop|3",
    ]
    assert all(item["containerType"] == "cup" for item in batch["items"])
    assert all(item["depositAmount"] == 20 for item in batch["items"])


def test_invoice_sequence_resets_per_invoice_and_store(context):
    client, _ = context
    tea_headers = login_headers(client, "tea_owner")
    bento_headers = login_headers(client, "bento_owner")

    first_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", cup_count=3)
    second_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", cup_count=2)
    other_invoice = create_qr_batch(client, tea_headers, invoice="OTHER-INVOICE", cup_count=1)
    other_store = create_qr_batch(client, bento_headers, invoice="SAME-INVOICE", cup_count=1)

    assert first_batch["startSequence"] == 1
    assert first_batch["endSequence"] == 3
    assert [item["qrValue"] for item in first_batch["items"]] == [
        "SAME-INVOICE|tea-shop|1",
        "SAME-INVOICE|tea-shop|2",
        "SAME-INVOICE|tea-shop|3",
    ]
    assert second_batch["startSequence"] == 4
    assert second_batch["endSequence"] == 5
    assert [item["qrValue"] for item in second_batch["items"]] == [
        "SAME-INVOICE|tea-shop|4",
        "SAME-INVOICE|tea-shop|5",
    ]
    assert other_invoice["startSequence"] == 1
    assert other_invoice["items"][0]["qrValue"] == "OTHER-INVOICE|tea-shop|1"
    assert other_store["startSequence"] == 1
    assert other_store["items"][0]["qrValue"] == "SAME-INVOICE|bento-shop|1"


def test_normal_return_creates_full_refund_and_rejects_duplicate_scan(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea_owner")
    bento_headers = login_headers(client, "bento_owner")
    qr = create_qr(client, tea_headers, "RETURN-001")

    returned = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )
    assert returned.status_code == 200
    assert returned.json()["refundAmount"] == 20
    assert returned.json()["refundReason"] == "normal"
    assert returned.json()["isExpired"] is False
    assert returned.json()["isAbnormal"] is False

    with SessionLocal() as db:
        loan = db.get(Loan, qr["loanId"])
        assert loan.status == "returned"
        assert loan.returned_store_id != loan.issued_store_id
        ledger = db.scalar(select(RefundLedger).where(RefundLedger.loan_id == loan.id))
        assert ledger.refund_amount == 20

    duplicate = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )
    assert duplicate.status_code == 409

    with SessionLocal() as db:
        duplicate_event = db.scalar(select(ScanEvent).where(ScanEvent.result == "duplicate_scan"))
        assert duplicate_event.reason == "already_returned"


def test_invalid_qr_is_rejected_and_recorded(context):
    client, SessionLocal = context
    headers = login_headers(client)

    response = client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": "not-a-real-token", "condition": "normal"},
    )
    assert response.status_code == 404

    with SessionLocal() as db:
        event = db.scalar(select(ScanEvent).where(ScanEvent.result == "invalid_qr"))
        assert event.reason == "invalid_qr"


def test_expired_and_damaged_returns_are_recovered_without_refund(context):
    client, SessionLocal = context
    headers = login_headers(client)

    expired_qr = create_qr(client, headers, "EXP-001")
    with SessionLocal() as db:
        loan = db.get(Loan, expired_qr["loanId"])
        loan.due_at = now_taipei() - timedelta(minutes=1)
        db.commit()

    expired_return = client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": expired_qr["qrValue"], "condition": "normal", "note": "late return"},
    )
    assert expired_return.status_code == 200
    assert expired_return.json()["refundAmount"] == 0
    assert expired_return.json()["refundReason"] == "expired"

    damaged_qr = create_qr(client, headers, "DMG-001")
    damaged_return = client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": damaged_qr["qrValue"], "condition": "damaged", "note": "cracked lid"},
    )
    assert damaged_return.status_code == 200
    assert damaged_return.json()["refundAmount"] == 0
    assert damaged_return.json()["refundReason"] == "damaged"


def test_merchant_stats_are_scoped_to_current_store(context):
    client, _ = context
    tea_headers = login_headers(client, "tea_owner")
    bento_headers = login_headers(client, "bento_owner")

    tea_qr = create_qr(client, tea_headers, "STAT-001")
    create_qr(client, tea_headers, "STAT-002")
    client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": tea_qr["qrValue"], "condition": "normal"},
    )

    params = stats_range()
    tea_sold = client.get("/merchant/stats/sold", headers=tea_headers, params=params)
    assert tea_sold.status_code == 200
    assert tea_sold.json()["totalCount"] == 2
    assert tea_sold.json()["depositTotal"] == 40

    bento_sold = client.get("/merchant/stats/sold", headers=bento_headers, params=params)
    assert bento_sold.status_code == 200
    assert bento_sold.json()["totalCount"] == 0

    bento_recovered = client.get("/merchant/stats/recovered", headers=bento_headers, params=params)
    assert bento_recovered.status_code == 200
    assert bento_recovered.json()["totalCount"] == 1
    assert bento_recovered.json()["crossStoreCount"] == 1

    tea_recovered = client.get("/merchant/stats/recovered", headers=tea_headers, params=params)
    assert tea_recovered.status_code == 200
    assert tea_recovered.json()["totalCount"] == 0


def test_government_views_expose_overview_store_stats_and_abnormal_events(context):
    client, SessionLocal = context
    headers = login_headers(client)
    qr = create_qr(client, headers, "VIEW-001")
    client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": qr["qrValue"], "condition": "polluted", "note": "sticky residue"},
    )

    with SessionLocal() as db:
        overview = db.execute(text("SELECT loans_total, returned_total, abnormal_total FROM v_gov_overview")).mappings().one()
        assert overview["loans_total"] == 1
        assert overview["returned_total"] == 1
        assert overview["abnormal_total"] == 1

        store = db.execute(text("SELECT issued_count, returned_count, abnormal_count FROM v_store_stats WHERE store_code = 'tea-shop'")).mappings().one()
        assert store["issued_count"] == 1
        assert store["returned_count"] == 1
        assert store["abnormal_count"] == 1

        abnormal = db.execute(text("SELECT reason, note FROM v_abnormal_events")).mappings().one()
        assert abnormal["reason"] == "polluted"
        assert abnormal["note"] == "sticky residue"
