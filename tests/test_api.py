import os
from datetime import timedelta

os.environ["AUTO_INIT_DB"] = "false"
os.environ["JWT_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.daily_reports import daily_report_path, read_report_rows
from app.database import Base, get_db
from app.main import app
from app.models import Loan, RefundLedger, ScanEvent
from app.seed import seed_demo_data
from app.time_utils import now_taipei
from app.views import create_sqlite_views


@pytest.fixture()
def context(tmp_path):
    os.environ["DAILY_REPORT_DIR"] = str(tmp_path / "reports")
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


def login_headers(client: TestClient, user_email: str = "tea.owner@example.com") -> dict[str, str]:
    response = client.post("/auth/login", json={"userEmail": user_email, "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def government_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/government/auth/login", json={"userEmail": "gov.admin@example.com", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def create_qr_batch(
    client: TestClient,
    headers: dict[str, str],
    invoice: str = "INV-001",
    cup_count: int = 1,
    container_type: str = "cup",
) -> dict:
    response = client.post(
        "/merchant/qr-codes",
        headers=headers,
        json={"invoiceCode": invoice, "containerType": container_type, "cupCount": cup_count},
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


def merchant_stats_range() -> dict[str, str]:
    today = now_taipei().date()
    return {
        "from": (today - timedelta(days=1)).isoformat(),
        "to": (today + timedelta(days=1)).isoformat(),
    }


def daily_stats_range() -> dict[str, str]:
    today = now_taipei().date().isoformat()
    return {"from": today, "to": today}


def test_login_success_and_failure(context):
    client, _ = context

    success = client.post("/auth/login", json={"userEmail": "tea.owner@example.com", "password": "password123"})
    assert success.status_code == 200
    assert success.json()["accessToken"]
    assert success.json()["store"]["code"] == "tea-shop"

    failure = client.post("/auth/login", json={"userEmail": "tea.owner@example.com", "password": "bad"})
    assert failure.status_code == 401

    invalid_email = client.post("/auth/login", json={"userEmail": "not-an-email", "password": "password123"})
    assert invalid_email.status_code == 422


def test_register_and_login_accept_email_field_aliases(context):
    client, _ = context

    register = client.post(
        "/auth/register",
        json={"userEmail": "123@gmail.com", "password": "12345678", "storeName": "登入測試店"},
    )
    assert register.status_code == 201

    login_lowercase_alias = client.post("/auth/login", json={"useremail": "123@gmail.com", "password": "12345678"})
    assert login_lowercase_alias.status_code == 200
    assert login_lowercase_alias.json()["store"]["name"] == "登入測試店"

    login_old_alias = client.post("/auth/login", json={"username": "123@gmail.com", "password": "12345678"})
    assert login_old_alias.status_code == 200

    register_lowercase_alias = client.post(
        "/auth/register",
        json={"useremail": "alias-register@example.com", "password": "12345678", "storeName": "登入測試店"},
    )
    assert register_lowercase_alias.status_code == 201
    assert register_lowercase_alias.json()["store"]["code"] == register.json()["store"]["code"]


def test_merchant_register_creates_store_user_and_token(context):
    client, _ = context

    response = client.post(
        "/auth/register",
        json={
            "userEmail": "new.merchant@example.com",
            "password": "password123",
            "storeName": "新店家",
        },
    )
    assert response.status_code == 201
    assert response.json()["accessToken"]
    assert response.json()["store"]["code"].startswith("store-")
    assert response.json()["store"]["name"] == "新店家"
    headers = {"Authorization": f"Bearer {response.json()['accessToken']}"}

    qr = client.post(
        "/merchant/qr-codes",
        headers=headers,
        json={"invoiceCode": "NEW-001", "containerType": "cup", "cupCount": 1},
    )
    assert qr.status_code == 201
    assert qr.json()["qrValue"] == f"NEW-001|{response.json()['store']['code']}|cup"

    duplicate_user = client.post(
        "/auth/register",
        json={
            "userEmail": "new.merchant@example.com",
            "password": "password123",
            "storeName": "另一新店",
        },
    )
    assert duplicate_user.status_code == 409

    same_store_second_user = client.post(
        "/auth/register",
        json={
            "userEmail": "another.merchant@example.com",
            "password": "password123",
            "storeName": "新店家",
        },
    )
    assert same_store_second_user.status_code == 201
    assert same_store_second_user.json()["store"]["code"] == response.json()["store"]["code"]


def test_government_login_and_role_isolation(context):
    client, _ = context
    gov_headers = government_headers(client)
    merchant_headers = login_headers(client)
    params = stats_range()

    overview = client.get("/government/overview", headers=gov_headers, params=params)
    assert overview.status_code == 200

    merchant_on_government = client.get("/government/overview", headers=merchant_headers, params=params)
    assert merchant_on_government.status_code == 403

    government_on_merchant = client.get("/merchant/stats/sold", headers=gov_headers, params=merchant_stats_range())
    assert government_on_merchant.status_code == 403


def test_government_register_creates_user_and_token(context):
    client, _ = context

    response = client.post(
        "/government/auth/register",
        json={"userEmail": "new.gov@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    assert response.json()["accessToken"]
    assert response.json()["user"]["userEmail"] == "new.gov@example.com"
    headers = {"Authorization": f"Bearer {response.json()['accessToken']}"}

    overview = client.get("/government/overview", headers=headers, params=stats_range())
    assert overview.status_code == 200

    duplicate = client.post(
        "/government/auth/register",
        json={"userEmail": "new.gov@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409


def test_create_qr_code_uses_cup_count_without_exposing_amounts(context):
    client, _ = context
    headers = login_headers(client)

    batch = create_qr_batch(client, headers, invoice="CUP-001", cup_count=3)

    assert batch["invoiceCode"] == "CUP-001"
    assert batch["storeCode"] == "tea-shop"
    assert batch["containerType"] == "cup"
    assert batch["addedCupCount"] == 3
    assert batch["totalCupCount"] == 3
    assert batch["returnedCount"] == 0
    assert batch["remainingCupCount"] == 3
    assert "totalDepositAmount" not in batch
    assert "depositAmount" not in batch
    assert batch["qrValue"] == "CUP-001|tea-shop|cup"


def test_create_qr_code_records_container_type_and_separates_types(context):
    client, _ = context
    headers = login_headers(client)

    meal_box_batch = create_qr_batch(
        client,
        headers,
        invoice="MEAL-BOX-001",
        cup_count=2,
        container_type="meal_box",
    )
    assert meal_box_batch["containerType"] == "meal_box"
    assert meal_box_batch["qrValue"] == "MEAL-BOX-001|tea-shop|meal_box"

    append_same_type = create_qr_batch(
        client,
        headers,
        invoice="MEAL-BOX-001",
        cup_count=1,
        container_type="meal_box",
    )
    assert append_same_type["totalCupCount"] == 3
    assert append_same_type["containerType"] == "meal_box"

    cup_batch = create_qr_batch(
        client,
        headers,
        invoice="MEAL-BOX-001",
        cup_count=1,
        container_type="cup",
    )
    assert cup_batch["containerType"] == "cup"
    assert cup_batch["loanId"] != meal_box_batch["loanId"]
    assert cup_batch["totalCupCount"] == 1
    assert cup_batch["qrValue"] == "MEAL-BOX-001|tea-shop|cup"


def test_invoice_qr_is_reused_and_count_accumulates_per_store(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")

    first_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", cup_count=3)
    second_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", cup_count=2)
    other_invoice = create_qr_batch(client, tea_headers, invoice="OTHER-INVOICE", cup_count=1)
    other_store = create_qr_batch(client, bento_headers, invoice="SAME-INVOICE", cup_count=1)

    assert first_batch["qrValue"] == "SAME-INVOICE|tea-shop|cup"
    assert first_batch["addedCupCount"] == 3
    assert first_batch["totalCupCount"] == 3
    assert second_batch["qrValue"] == "SAME-INVOICE|tea-shop|cup"
    assert second_batch["addedCupCount"] == 2
    assert second_batch["totalCupCount"] == 5
    assert other_invoice["totalCupCount"] == 1
    assert other_invoice["qrValue"] == "OTHER-INVOICE|tea-shop|cup"
    assert other_store["totalCupCount"] == 1
    assert other_store["qrValue"] == "SAME-INVOICE|bento-shop|cup"

    today = now_taipei().date()
    rows = read_report_rows(today, today)
    sold_rows = [row for row in rows if row["eventType"] == "sold"]
    assert daily_report_path(today).exists()
    assert sum(int(row["cupCount"]) for row in sold_rows if row["storeCode"] == "tea-shop") == 6
    assert sum(int(row["cupCount"]) for row in sold_rows if row["storeCode"] == "bento-shop") == 1


def test_normal_return_creates_full_refund_and_rejects_duplicate_scan(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")
    qr = create_qr(client, tea_headers, "RETURN-001")

    returned = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
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

    today = now_taipei().date()
    rows = read_report_rows(today, today)
    recovered_rows = [row for row in rows if row["eventType"] == "recovered" and row["storeCode"] == "bento-shop"]
    assert len(recovered_rows) == 1
    assert recovered_rows[0]["isExpired"] == "false"
    assert recovered_rows[0]["isAbnormal"] == "false"
    assert recovered_rows[0]["isCrossStore"] == "true"

    duplicate = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
    )
    assert duplicate.status_code == 409

    with SessionLocal() as db:
        duplicate_event = db.scalar(select(ScanEvent).where(ScanEvent.result == "duplicate_scan"))
        assert duplicate_event.reason == "already_returned"


def test_return_scan_request_only_accepts_qr_value(context):
    client, _ = context
    headers = login_headers(client)
    qr = create_qr(client, headers, "QR-ONLY-001")

    response = client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": qr["qrValue"], "condition": "normal"},
    )

    assert response.status_code == 422


def test_invoice_qr_returns_one_cup_per_scan(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")
    qr = create_qr_batch(client, tea_headers, "PARTIAL-001", cup_count=3)

    first_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
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
        json={"qrValue": qr["qrValue"]},
    )
    assert second_return.status_code == 200
    assert second_return.json()["status"] == "partial_returned"
    assert second_return.json()["returnedCount"] == 2
    assert second_return.json()["remainingCupCount"] == 1

    final_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
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
        json={"qrValue": "not-a-real-token"},
    )
    assert response.status_code == 404

    with SessionLocal() as db:
        event = db.scalar(select(ScanEvent).where(ScanEvent.result == "invalid_qr"))
        assert event.reason == "invalid_qr"


def test_expired_returns_are_recovered_without_refund(context):
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
        json={"qrValue": expired_qr["qrValue"]},
    )
    assert expired_return.status_code == 200
    assert expired_return.json()["refundReason"] == "expired"
    assert expired_return.json()["isExpired"] is True
    assert expired_return.json()["isAbnormal"] is False
    assert "refundAmount" not in expired_return.json()


def test_merchant_stats_are_scoped_to_current_store(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")

    tea_qr = create_qr(client, tea_headers, "STAT-001")
    second_tea_qr = create_qr(client, tea_headers, "STAT-002")
    tea_meal_box_qr = create_qr_batch(
        client,
        tea_headers,
        invoice="STAT-MEAL-001",
        cup_count=2,
        container_type="meal_box",
    )
    client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": tea_qr["qrValue"]},
    )
    client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": tea_meal_box_qr["qrValue"]},
    )

    with SessionLocal() as db:
        first_loan = db.get(Loan, tea_qr["loanId"])
        second_loan = db.get(Loan, second_tea_qr["loanId"])
        meal_box_loan = db.get(Loan, tea_meal_box_qr["loanId"])
        first_loan.returned_count = 42
        second_loan.cup_count = 99
        meal_box_loan.cup_count = 88
        db.commit()

    params = merchant_stats_range()
    today = now_taipei().date().isoformat()
    tea_sold = client.get("/merchant/stats/sold", headers=tea_headers, params=params)
    assert tea_sold.status_code == 200
    assert len(tea_sold.json()["rows"]) == 3
    assert "containerType" not in tea_sold.json()
    tea_sold_today = next(row for row in tea_sold.json()["rows"] if row["statDate"] == today)
    assert tea_sold_today["totalCount"] == 4
    assert tea_sold_today["cupCount"] == 2
    assert tea_sold_today["mealBoxCount"] == 2
    assert "depositTotal" not in tea_sold.json()

    bento_sold = client.get("/merchant/stats/sold", headers=bento_headers, params=params)
    assert bento_sold.status_code == 200
    assert len(bento_sold.json()["rows"]) == 3
    assert sum(row["totalCount"] for row in bento_sold.json()["rows"]) == 0

    bento_recovered = client.get("/merchant/stats/recovered", headers=bento_headers, params=params)
    assert bento_recovered.status_code == 200
    assert len(bento_recovered.json()["rows"]) == 3
    assert "containerType" not in bento_recovered.json()
    bento_recovered_today = next(row for row in bento_recovered.json()["rows"] if row["statDate"] == today)
    assert bento_recovered_today["totalCount"] == 2
    assert bento_recovered_today["cupCount"] == 1
    assert bento_recovered_today["mealBoxCount"] == 1
    assert bento_recovered_today["crossStoreCount"] == 2

    tea_recovered = client.get("/merchant/stats/recovered", headers=tea_headers, params=params)
    assert tea_recovered.status_code == 200
    assert len(tea_recovered.json()["rows"]) == 3
    assert sum(row["totalCount"] for row in tea_recovered.json()["rows"]) == 0


def test_government_views_expose_overview_store_stats_and_abnormal_events(context):
    client, SessionLocal = context
    headers = login_headers(client)
    qr = create_qr(client, headers, "VIEW-001")
    with SessionLocal() as db:
        loan = db.get(Loan, qr["loanId"])
        loan.due_at = now_taipei() - timedelta(minutes=1)
        db.commit()

    client.post(
        "/merchant/returns/scan",
        headers=headers,
        json={"qrValue": qr["qrValue"]},
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
        assert abnormal["reason"] == "expired"
        assert abnormal["note"] is None

    today = now_taipei().date()
    rows = read_report_rows(today, today)
    assert any(row["eventType"] == "sold" and row["storeCode"] == "tea-shop" for row in rows)
    assert any(
        row["eventType"] == "recovered" and row["storeCode"] == "tea-shop" and row["isExpired"] == "true"
        for row in rows
    )


def test_government_read_only_apis_cover_overview_stores_invoices_and_anomalies(context):
    client, _ = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")
    gov_headers = government_headers(client)

    qr = create_qr_batch(client, tea_headers, "GOV-001", cup_count=2)
    client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
    )
    duplicate = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": "bad-government-token"},
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

    daily_sold = client.get("/government/daily/sold", headers=gov_headers, params=daily_stats_range())
    assert daily_sold.status_code == 200
    tea_daily_sold = next(row for row in daily_sold.json()["rows"] if row["storeCode"] == "tea-shop")
    assert tea_daily_sold["soldCount"] == 2

    daily_recovered = client.get("/government/daily/recovered", headers=gov_headers, params=daily_stats_range())
    assert daily_recovered.status_code == 200
    bento_daily_recovered = next(row for row in daily_recovered.json()["rows"] if row["storeCode"] == "bento-shop")
    assert bento_daily_recovered["recoveredCount"] == 1
    assert bento_daily_recovered["normalCount"] == 1
    assert bento_daily_recovered["crossStoreCount"] == 1

    invoices = client.get("/government/invoices", headers=gov_headers, params=params)
    assert invoices.status_code == 200
    invoice = next(item for item in invoices.json()["invoices"] if item["invoiceCode"] == "GOV-001")
    assert invoice["qrValue"] == "GOV-001|tea-shop|cup"
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
