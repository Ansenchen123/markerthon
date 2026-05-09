import os
from concurrent.futures import ThreadPoolExecutor
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
from app.models import Loan, RefundLedger, ScanEvent, Store
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
    item_count: int = 1,
    category: str = "cup",
) -> dict:
    response = client.post(
        "/merchant/qr-codes",
        headers=headers,
        json={"invoiceCode": invoice, "category": category, "count": item_count},
    )
    assert response.status_code == 201
    return response.json()


def create_qr(client: TestClient, headers: dict[str, str], invoice: str = "INV-001") -> dict:
    return create_qr_batch(client, headers, invoice=invoice, item_count=1)


def stats_range() -> dict[str, str]:
    now = now_taipei()
    return {
        "from": (now - timedelta(days=1)).isoformat(),
        "to": (now + timedelta(days=1)).isoformat(),
    }


def merchant_stats_range(store_id: int) -> dict[str, str]:
    today = now_taipei().date()
    return {
        "storeId": str(store_id),
        "from": (today - timedelta(days=1)).isoformat(),
        "to": (today + timedelta(days=1)).isoformat(),
    }


def daily_stats_range() -> dict[str, str]:
    today = now_taipei().date().isoformat()
    return {"from": today, "to": today}


def month_params() -> dict[str, str]:
    now = now_taipei()
    return {"year": str(now.year), "month": str(now.month)}


def count_for_category(row: dict, category: str) -> int:
    return next(item["count"] for item in row["categoryCounts"] if item["category"] == category)


def test_login_success_and_failure(context):
    client, _ = context

    success = client.post("/auth/login", json={"userEmail": "tea.owner@example.com", "password": "password123"})
    assert success.status_code == 200
    assert success.json()["accessToken"]
    assert success.json()["store"]["code"] == "tea-shop"
    assert success.json()["store"]["region"] == "台北市大安區"

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
    assert register.json()["store"]["region"] == "未設定"

    login_lowercase_alias = client.post("/auth/login", json={"useremail": "123@gmail.com", "password": "12345678"})
    assert login_lowercase_alias.status_code == 200
    assert login_lowercase_alias.json()["store"]["name"] == "登入測試店"
    assert login_lowercase_alias.json()["store"]["region"] == "未設定"

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
            "region": "台北市信義區",
        },
    )
    assert response.status_code == 201
    assert response.json()["accessToken"]
    assert response.json()["store"]["code"].startswith("store-")
    assert response.json()["store"]["name"] == "新店家"
    assert response.json()["store"]["region"] == "台北市信義區"
    headers = {"Authorization": f"Bearer {response.json()['accessToken']}"}

    qr = client.post(
        "/merchant/qr-codes",
        headers=headers,
        json={"invoiceCode": "NEW-001", "category": "cup", "count": 1},
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
    assert same_store_second_user.json()["store"]["region"] == "台北市信義區"


def test_government_login_and_role_isolation(context):
    client, _ = context
    gov_headers = government_headers(client)
    merchant_headers = login_headers(client)
    params = month_params()

    monthly_usage = client.get("/government/web/monthly-usage", headers=gov_headers, params=params)
    assert monthly_usage.status_code == 200

    merchant_on_government = client.get("/government/web/monthly-usage", headers=merchant_headers, params=params)
    assert merchant_on_government.status_code == 403

    government_on_merchant = client.get(
        "/merchant/stats/sold",
        headers=gov_headers,
        params=merchant_stats_range(1),
    )
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

    monthly_usage = client.get("/government/web/monthly-usage", headers=headers, params=month_params())
    assert monthly_usage.status_code == 200

    duplicate = client.post(
        "/government/auth/register",
        json={"userEmail": "new.gov@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409


def test_create_qr_code_uses_item_count_without_exposing_amounts(context):
    client, _ = context
    headers = login_headers(client)

    batch = create_qr_batch(client, headers, invoice="CUP-001", item_count=3)

    assert batch["invoiceCode"] == "CUP-001"
    assert batch["storeCode"] == "tea-shop"
    assert batch["category"] == "cup"
    assert batch["addedCount"] == 3
    assert batch["totalCount"] == 3
    assert batch["returnedCount"] == 0
    assert batch["remainingCount"] == 3
    assert "totalDepositAmount" not in batch
    assert "depositAmount" not in batch
    assert batch["qrValue"] == "CUP-001|tea-shop|cup"


def test_create_qr_code_records_category_and_separates_categories(context):
    client, _ = context
    headers = login_headers(client)

    meal_box_batch = create_qr_batch(
        client,
        headers,
        invoice="MEAL-BOX-001",
        item_count=2,
        category="meal_box",
    )
    assert meal_box_batch["category"] == "meal_box"
    assert meal_box_batch["qrValue"] == "MEAL-BOX-001|tea-shop|meal_box"

    append_same_type = create_qr_batch(
        client,
        headers,
        invoice="MEAL-BOX-001",
        item_count=1,
        category="meal_box",
    )
    assert append_same_type["totalCount"] == 3
    assert append_same_type["category"] == "meal_box"

    cup_batch = create_qr_batch(
        client,
        headers,
        invoice="MEAL-BOX-001",
        item_count=1,
        category="cup",
    )
    assert cup_batch["category"] == "cup"
    assert cup_batch["loanId"] != meal_box_batch["loanId"]
    assert cup_batch["totalCount"] == 1
    assert cup_batch["qrValue"] == "MEAL-BOX-001|tea-shop|cup"


def test_daily_report_header_is_written_once_for_parallel_category_creates(context):
    client, _ = context
    headers = login_headers(client)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda category: create_qr_batch(
                    client,
                    headers,
                    invoice="PARALLEL-HEADER-001",
                    item_count=1,
                    category=category,
                ),
                ("cup", "meal_box"),
            )
        )

    assert {result["category"] for result in results} == {"cup", "meal_box"}

    today = now_taipei().date()
    report_text = daily_report_path(today).read_text(encoding="utf-8")
    assert report_text.count("eventType,occurredAt,loanId") == 1

    rows = read_report_rows(today, today)
    sold_rows = [row for row in rows if row["invoiceCode"] == "PARALLEL-HEADER-001"]
    assert len(sold_rows) == 2


def test_invoice_qr_is_reused_and_count_accumulates_per_store(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")

    first_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", item_count=3)
    second_batch = create_qr_batch(client, tea_headers, invoice="SAME-INVOICE", item_count=2)
    other_invoice = create_qr_batch(client, tea_headers, invoice="OTHER-INVOICE", item_count=1)
    other_store = create_qr_batch(client, bento_headers, invoice="SAME-INVOICE", item_count=1)

    assert first_batch["qrValue"] == "SAME-INVOICE|tea-shop|cup"
    assert first_batch["addedCount"] == 3
    assert first_batch["totalCount"] == 3
    assert second_batch["qrValue"] == "SAME-INVOICE|tea-shop|cup"
    assert second_batch["addedCount"] == 2
    assert second_batch["totalCount"] == 5
    assert other_invoice["totalCount"] == 1
    assert other_invoice["qrValue"] == "OTHER-INVOICE|tea-shop|cup"
    assert other_store["totalCount"] == 1
    assert other_store["qrValue"] == "SAME-INVOICE|bento-shop|cup"

    today = now_taipei().date()
    rows = read_report_rows(today, today)
    sold_rows = [row for row in rows if row["eventType"] == "sold"]
    assert daily_report_path(today).exists()
    assert sum(int(row["count"]) for row in sold_rows if row["storeCode"] == "tea-shop") == 6
    assert sum(int(row["count"]) for row in sold_rows if row["storeCode"] == "bento-shop") == 1


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
        assert loan.item_count == 1
        assert loan.returned_count == 1
        assert loan.remaining_count == 0
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


def test_invoice_qr_returns_one_container_per_scan(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")
    qr = create_qr_batch(client, tea_headers, "PARTIAL-001", item_count=3)

    first_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
    )
    assert first_return.status_code == 200
    assert first_return.json()["status"] == "partial_returned"
    assert "refundAmount" not in first_return.json()
    assert first_return.json()["count"] == 1
    assert first_return.json()["returnedCount"] == 1
    assert first_return.json()["remainingCount"] == 2

    with SessionLocal() as db:
        loan = db.get(Loan, qr["loanId"])
        assert loan.item_count == 3
        assert loan.returned_count == 1
        assert loan.remaining_count == 2

    second_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
    )
    assert second_return.status_code == 200
    assert second_return.json()["status"] == "partial_returned"
    assert second_return.json()["returnedCount"] == 2
    assert second_return.json()["remainingCount"] == 1

    with SessionLocal() as db:
        loan = db.get(Loan, qr["loanId"])
        assert loan.item_count == 3
        assert loan.returned_count == 2
        assert loan.remaining_count == 1

    final_return = client.post(
        "/merchant/returns/scan",
        headers=bento_headers,
        json={"qrValue": qr["qrValue"]},
    )
    assert final_return.status_code == 200
    assert final_return.json()["status"] == "returned"
    assert final_return.json()["returnedCount"] == 3
    assert final_return.json()["remainingCount"] == 0

    with SessionLocal() as db:
        loan = db.get(Loan, qr["loanId"])
        assert loan.item_count == 3
        assert loan.returned_count == 3
        assert loan.remaining_count == 0
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
        item_count=2,
        category="meal_box",
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
        tea_store_id, tea_store_name = db.execute(
            select(Store.id, Store.name).where(Store.code == "tea-shop")
        ).one()
        bento_store_id, bento_store_name = db.execute(
            select(Store.id, Store.name).where(Store.code == "bento-shop")
        ).one()
        first_loan.returned_count = 42
        second_loan.item_count = 99
        meal_box_loan.item_count = 88
        db.commit()

    tea_params = merchant_stats_range(tea_store_id)
    bento_params = merchant_stats_range(bento_store_id)
    today = now_taipei().date().isoformat()
    tea_sold = client.get("/merchant/stats/sold", headers=tea_headers, params=tea_params)
    assert tea_sold.status_code == 200
    assert tea_sold.json()["storeId"] == tea_store_id
    assert tea_sold.json()["storeName"] == tea_store_name
    assert len(tea_sold.json()["rows"]) == 3
    assert "category" not in tea_sold.json()
    assert tea_sold.json()["remainingCount"] == 2
    tea_sold_today = next(row for row in tea_sold.json()["rows"] if row["statDate"] == today)
    assert tea_sold_today["totalCount"] == 4
    assert "remainingCount" not in tea_sold_today
    assert count_for_category(tea_sold_today, "cup") == 2
    assert count_for_category(tea_sold_today, "meal_box") == 2
    assert "depositTotal" not in tea_sold.json()

    legacy_name_params = {**tea_params, "storeName": tea_store_name}
    legacy_name_params.pop("storeId")
    legacy_name_response = client.get("/merchant/stats/sold", headers=tea_headers, params=legacy_name_params)
    assert legacy_name_response.status_code == 422

    wrong_store = client.get("/merchant/stats/sold", headers=tea_headers, params=bento_params)
    assert wrong_store.status_code == 403

    bento_sold = client.get("/merchant/stats/sold", headers=bento_headers, params=bento_params)
    assert bento_sold.status_code == 200
    assert bento_sold.json()["remainingCount"] == 0
    assert len(bento_sold.json()["rows"]) == 3
    assert sum(row["totalCount"] for row in bento_sold.json()["rows"]) == 0

    bento_recovered = client.get("/merchant/stats/recovered", headers=bento_headers, params=bento_params)
    assert bento_recovered.status_code == 200
    assert bento_recovered.json()["storeId"] == bento_store_id
    assert bento_recovered.json()["storeName"] == bento_store_name
    assert len(bento_recovered.json()["rows"]) == 3
    assert "category" not in bento_recovered.json()
    bento_recovered_today = next(row for row in bento_recovered.json()["rows"] if row["statDate"] == today)
    assert bento_recovered_today["totalCount"] == 2
    assert count_for_category(bento_recovered_today, "cup") == 1
    assert count_for_category(bento_recovered_today, "meal_box") == 1
    assert bento_recovered_today["crossStoreCount"] == 2

    tea_recovered = client.get("/merchant/stats/recovered", headers=tea_headers, params=tea_params)
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


def test_legacy_government_read_only_apis_are_removed(context):
    client, _ = context
    gov_headers = government_headers(client)
    legacy_endpoints = [
        ("/government/overview", stats_range()),
        ("/government/stores", stats_range()),
        ("/government/daily/sold", daily_stats_range()),
        ("/government/daily/recovered", daily_stats_range()),
        ("/government/invoices", stats_range()),
        ("/government/invoices/1", {}),
        ("/government/anomalies", stats_range()),
        ("/government/web/top-cup-stores", month_params()),
    ]

    for path, params in legacy_endpoints:
        response = client.get(path, headers=gov_headers, params=params)
        assert response.status_code == 404


def test_government_web_apis_cover_monthly_dashboard_and_store_status(context):
    client, SessionLocal = context
    tea_headers = login_headers(client, "tea.owner@example.com")
    bento_headers = login_headers(client, "bento.owner@example.com")
    gov_headers = government_headers(client)

    tea_cup = create_qr_batch(client, tea_headers, "WEB-TEA-CUP", item_count=4)
    tea_meal_box = create_qr_batch(
        client,
        tea_headers,
        "WEB-TEA-MEAL",
        item_count=2,
        category="meal_box",
    )
    bento_cup = create_qr_batch(client, bento_headers, "WEB-BENTO-CUP", item_count=1)
    client.post("/merchant/returns/scan", headers=tea_headers, json={"qrValue": tea_cup["qrValue"]})
    client.post("/merchant/returns/scan", headers=tea_headers, json={"qrValue": tea_meal_box["qrValue"]})
    client.post("/merchant/returns/scan", headers=bento_headers, json={"qrValue": bento_cup["qrValue"]})

    with SessionLocal() as db:
        tea_store_name = db.scalar(select(Store.name).where(Store.code == "tea-shop"))

    params = month_params()
    usage = client.get("/government/web/monthly-usage", headers=gov_headers, params=params)
    assert usage.status_code == 200
    assert usage.json()["issuedCount"] == 7
    assert usage.json()["returnedCount"] == 3
    assert usage.json()["remainingCount"] == 4
    assert usage.json()["recoveryRate"] == 0.4286
    assert any(row["issuedCount"] == 7 for row in usage.json()["daily"])

    enterprise_counts = client.get("/government/web/enterprise-counts", headers=gov_headers, params=params)
    assert enterprise_counts.status_code == 200
    assert enterprise_counts.json()["monthJoinedCount"] == 3
    assert enterprise_counts.json()["totalEnterpriseCount"] == 3

    regions = client.get("/government/web/region-distribution", headers=gov_headers)
    assert regions.status_code == 200
    assert regions.json()["totalEnterpriseCount"] == 3
    region_counts = {row["region"]: row["enterpriseCount"] for row in regions.json()["regions"]}
    assert region_counts["台北市大安區"] == 1
    assert region_counts["台北市中山區"] == 1
    assert region_counts["新北市板橋區"] == 1

    ranking = client.get("/government/web/top-stores", headers=gov_headers, params={**params, "limit": "2"})
    assert ranking.status_code == 200
    assert "category" not in ranking.json()
    assert ranking.json()["rankings"][0]["storeCode"] == "tea-shop"
    assert ranking.json()["rankings"][0]["issuedCount"] == 6
    assert ranking.json()["rankings"][0]["returnedCount"] == 2
    assert ranking.json()["rankings"][0]["remainingCount"] == 4
    assert ranking.json()["rankings"][0]["region"] == "台北市大安區"

    store_status = client.get(
        "/government/web/stores",
        headers=gov_headers,
        params={**params, "storeName": tea_store_name},
    )
    assert store_status.status_code == 200
    assert store_status.json()["store"]["code"] == "tea-shop"
    assert store_status.json()["store"]["region"] == "台北市大安區"
    assert store_status.json()["issuedCount"] == 6
    assert store_status.json()["returnedCount"] == 2
    assert store_status.json()["recoveredCount"] == 2
    assert store_status.json()["remainingCount"] == 4
    assert store_status.json()["cupIssuedCount"] == 4
    assert store_status.json()["cupReturnedCount"] == 1
    assert store_status.json()["mealBoxIssuedCount"] == 2
    assert store_status.json()["mealBoxReturnedCount"] == 1

    missing_store = client.get(
        "/government/web/stores",
        headers=gov_headers,
        params={**params, "storeName": "不存在店家"},
    )
    assert missing_store.status_code == 404

    legacy_id_store = client.get("/government/web/stores/1", headers=gov_headers, params=params)
    assert legacy_id_store.status_code == 404
