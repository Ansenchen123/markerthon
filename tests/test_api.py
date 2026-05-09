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


def government_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/government/auth/login", json={"username": "gov_admin", "password": "password123"})
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
    return create_qr_batch(client, headers, invoice=invoice, cup_count=1)


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


def test_government_login_and_role_isolation(context):
    client, _ = context
    gov_headers = government_headers(client)
    merchant_headers = login_headers(client)
    params = stats_range()

    overview = client.get("/government/overview", headers=gov_headers, params=params)
    assert overview.status_code == 200

    merchant_on_government = client.get("/government/overview", headers=merchant_headers, params=params)
    assert merchant_on_government.status_code == 403

    government_on_merchant = client.get("/merchant/stats/sold", headers=gov_headers, params=params)
    assert government_on_merchant.status_code == 403


def test_create_qr_code_uses_cup_count_without_exposing_amounts(context):
    client, _ = context
    headers = login_headers(client)

    batch = create_qr_batch(client, headers, invoice="CUP-001", cup_count=3)

    assert batch["invoiceCode"] == "CUP-001"
    assert batch["storeCode"] == "tea-shop"
    assert batch["addedCupCount"] == 3
    assert batch["totalCupCount"] == 3
    assert batch["returnedCount"] == 0
    assert batch["remainingCupCount"] == 3
    assert "totalDepositAmount" not in batch
    assert "depositAmount" not in batch
    assert batch["qrValue"] == "CUP-001|tea-shop"


def test_invoice_qr_is_reused_and_count_accumulates_per_store(context):
    client, _ = context
    tea_headers = login_headers(client, "tea_owner")
    bento_headers = login_headers(client, "bento_owner")

    first_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", cup_count=3)
    second_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", cup_count=2)
    other_invoice = create_qr_batch(client, tea_headers, invoice="OTHER-INVOICE", cup_count=1)
    other_store = create_qr_batch(client, bento_headers, invoice="SAME-INVOICE", cup_count=1)

    assert first_batch["qrValue"] == "SAME-INVOICE|tea-shop"
    assert first_batch["addedCupCount"] == 3
    assert first_batch["totalCupCount"] == 3
    assert second_batch["qrValue"] == "SAME-INVOICE|tea-shop"
    assert second_batch["addedCupCount"] == 2
    assert second_batch["totalCupCount"] == 5
    assert other_invoice["totalCupCount"] == 1
    assert other_invoice["qrValue"] == "OTHER-INVOICE|tea-shop"
    assert other_store["totalCupCount"] == 1
    assert other_store["qrValue"] == "SAME-INVOICE|bento-shop"


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
    assert "refundAmount" not in returned.json()
    assert "depositAmount" not in returned.json()
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


def test_invoice_qr_returns_one_cup_per_scan(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea_owner")
    bento_headers = login_headers(client, "bento_owner")
    qr = create_qr_batch(client, tea_headers, "PARTIAL-001", cup_count=3)

    first_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )
    assert first_return.status_code == 200
    assert first_return.json()["status"] == "partial_returned"
    assert "refundAmount" not in first_return.json()
    assert first_return.json()["cupCount"] == 1
    assert first_return.json()["returnedCount"] == 1
    assert first_return.json()["remainingCupCount"] == 2

    second_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )
    assert second_return.status_code == 200
    assert second_return.json()["status"] == "partial_returned"
    assert second_return.json()["returnedCount"] == 2
    assert second_return.json()["remainingCupCount"] == 1

    final_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )
    assert final_return.status_code == 200
    assert final_return.json()["status"] == "returned"
    assert final_return.json()["returnedCount"] == 3
    assert final_return.json()["remainingCupCount"] == 0

    with SessionLocal() as db:
        loan = db.get(Loan, qr["loanId"])
        assert loan.cup_count == 3
        assert loan.returned_count == 3
        assert loan.status == "returned"
        ledger = db.scalar(select(RefundLedger).where(RefundLedger.loan_id == loan.id))
        assert ledger.refund_amount == 60


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
    assert expired_return.json()["refundReason"] == "expired"
    assert "refundAmount" not in expired_return.json()

    damaged_qr = create_qr(client, headers, "DMG-001")
    damaged_return = client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": damaged_qr["qrValue"], "condition": "damaged", "note": "cracked lid"},
    )
    assert damaged_return.status_code == 200
    assert damaged_return.json()["refundReason"] == "damaged"
    assert "refundAmount" not in damaged_return.json()


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
    assert "depositTotal" not in tea_sold.json()

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


def test_government_read_only_apis_cover_overview_stores_invoices_and_anomalies(context):
    client, _ = context
    tea_headers = login_headers(client, "tea_owner")
    bento_headers = login_headers(client, "bento_owner")
    gov_headers = government_headers(client)

    qr = create_qr_batch(client, tea_headers, "GOV-001", cup_count=2)
    client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )
    duplicate = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": "bad-government-token", "condition": "normal"},
    )
    assert duplicate.status_code == 404

    params = stats_range()
    overview = client.get("/government/overview", headers=gov_headers, params=params)
    assert overview.status_code == 200
    assert overview.json()["issuedCupCount"] == 2
    assert overview.json()["returnedCupCount"] == 1
    assert overview.json()["remainingCupCount"] == 1
    assert overview.json()["partialReturnedInvoiceCount"] == 1
    assert "depositTotal" not in overview.json()

    stores = client.get("/government/stores", headers=gov_headers, params=params)
    assert stores.status_code == 200
    tea_store = next(store for store in stores.json()["stores"] if store["storeCode"] == "tea-shop")
    bento_store = next(store for store in stores.json()["stores"] if store["storeCode"] == "bento-shop")
    assert tea_store["issuedCupCount"] == 2
    assert bento_store["returnedCupCount"] == 1
    assert bento_store["crossStoreReturnedCount"] == 1

    invoices = client.get("/government/invoices", headers=gov_headers, params=params)
    assert invoices.status_code == 200
    invoice = next(item for item in invoices.json()["invoices"] if item["invoiceCode"] == "GOV-001")
    assert invoice["qrValue"] == "GOV-001|tea-shop"
    assert invoice["totalCupCount"] == 2
    assert invoice["returnedCount"] == 1
    assert invoice["remainingCupCount"] == 1

    detail = client.get(f"/government/invoices/{qr['loanId']}", headers=gov_headers)
    assert detail.status_code == 200
    assert detail.json()["invoiceCode"] == "GOV-001"
    assert detail.json()["returnedStoreCode"] == "bento-shop"
    assert len(detail.json()["scanEvents"]) == 1

    anomalies = client.get("/government/anomalies", headers=gov_headers, params=params)
    assert anomalies.status_code == 200
    assert any(item["result"] == "invalid_qr" for item in anomalies.json()["anomalies"])
