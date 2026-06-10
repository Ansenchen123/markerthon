from contextlib import contextmanager
from datetime import datetime, time, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.routers.merchant as merchant_router
from app.daily_reports import daily_report_path, read_report_rows, rebuild_daily_report_csvs
from app.database import SessionLocal
from app.init_db import init_db
from app.main import app
from app.models import Loan, RefundLedger, ScanEvent
from app.seed import DEMO_PASSWORD, seed_demo_data
from app.time_utils import now_taipei


MERCHANT_EMAILS = {
    "tea": "tea.owner@example.com",
    "bento": "bento.owner@example.com",
    "cafe": "cafe.owner@example.com",
}
STORE_ORDER = ["tea", "bento", "cafe"]
STORE_CODES = {
    "tea": "tea-shop",
    "bento": "bento-shop",
    "cafe": "cafe-shop",
}
DEMO_INVOICE_PREFIX = "DEMO-"


@contextmanager
def fake_merchant_time(value: datetime):
    original = merchant_router.now_taipei
    merchant_router.now_taipei = lambda: value
    try:
        yield
    finally:
        merchant_router.now_taipei = original


def _request_json(response, expected_status: int) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise RuntimeError(f"Expected {expected_status}, got {response.status_code}: {response.text}")
    if not response.content:
        return {}
    return response.json()


def _login(client: TestClient, user_email: str, path: str = "/auth/login") -> dict[str, str]:
    response = client.post(path, json={"userEmail": user_email, "password": DEMO_PASSWORD})
    body = _request_json(response, 200)
    return {"Authorization": f"Bearer {body['accessToken']}"}


def _merchant_session(client: TestClient, user_email: str) -> dict[str, Any]:
    response = client.post("/auth/login", json={"userEmail": user_email, "password": DEMO_PASSWORD})
    body = _request_json(response, 200)
    return {
        "headers": {"Authorization": f"Bearer {body['accessToken']}"},
        "storeId": body["store"]["id"],
        "storeName": body["store"]["name"],
    }


def _at(day, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute))


def reset_demo_business_data(db: Session) -> None:
    loan_ids = list(db.scalars(select(Loan.id).where(Loan.invoice_code.like(f"{DEMO_INVOICE_PREFIX}%"))))
    if not loan_ids:
        return

    db.execute(delete(RefundLedger).where(RefundLedger.loan_id.in_(loan_ids)))
    db.execute(delete(ScanEvent).where(ScanEvent.loan_id.in_(loan_ids)))
    db.execute(delete(Loan).where(Loan.id.in_(loan_ids)))
    db.commit()


def create_demo_flow(client: TestClient, *, days: int = 5) -> dict[str, Any]:
    today = now_taipei().date()
    start_date = today - timedelta(days=days - 1)
    merchant_sessions = {key: _merchant_session(client, email) for key, email in MERCHANT_EMAILS.items()}
    merchant_headers = {key: session["headers"] for key, session in merchant_sessions.items()}
    merchant_store_ids = {key: session["storeId"] for key, session in merchant_sessions.items()}
    government_headers = _login(client, "gov.admin@example.com", path="/government/auth/login")
    created_batches: list[dict[str, Any]] = []

    sales_counts = [
        {"tea": 5, "bento": 3, "cafe": 2},
        {"tea": 4, "bento": 5, "cafe": 3},
        {"tea": 6, "bento": 4, "cafe": 2},
        {"tea": 3, "bento": 4, "cafe": 4},
        {"tea": 5, "bento": 3, "cafe": 3},
    ]

    for day_index in range(days):
        order_date = start_date + timedelta(days=day_index)
        days_ago = (today - order_date).days
        for store_index, store_key in enumerate(STORE_ORDER):
            item_count = sales_counts[day_index % len(sales_counts)][store_key]
            invoice_code = f"{DEMO_INVOICE_PREFIX}{order_date.strftime('%Y%m%d')}-{STORE_CODES[store_key].upper()}-01"
            issue_time = _at(order_date, 9 + store_index, 15)

            with fake_merchant_time(issue_time):
                batch = _request_json(
                    client.post(
                        "/merchant/qr-codes",
                        headers=merchant_headers[store_key],
                        json={"invoiceCode": invoice_code, "category": "cup", "count": item_count},
                    ),
                    201,
                )
            created_batches.append({"store": store_key, "date": order_date, "daysAgo": days_ago, **batch})

            if days_ago >= 3:
                planned_returns = item_count - 1
            elif days_ago >= 1:
                planned_returns = max(item_count - 2, 1)
            else:
                planned_returns = min(item_count, 1)

            for scan_index in range(planned_returns):
                if days_ago >= 4 and scan_index == planned_returns - 1:
                    return_date = today
                    return_hour = 16
                else:
                    return_date = min(order_date + timedelta(days=1), today)
                    return_hour = 12 + scan_index

                receiver_key = STORE_ORDER[(store_index + scan_index + 1) % len(STORE_ORDER)]
                with fake_merchant_time(_at(return_date, return_hour, 30)):
                    _request_json(
                        client.post(
                            "/merchant/returns/scan",
                            headers=merchant_headers[receiver_key],
                            json={"qrValue": batch["qrValue"]},
                        ),
                        200,
                    )

    duplicate_invoice = f"{DEMO_INVOICE_PREFIX}{today.strftime('%Y%m%d')}-DUPLICATE-CHECK"
    with fake_merchant_time(_at(today, 17, 0)):
        duplicate_target = _request_json(
            client.post(
                "/merchant/qr-codes",
                headers=merchant_headers["tea"],
                json={"invoiceCode": duplicate_invoice, "category": "cup", "count": 1},
            ),
            201,
        )
    created_batches.append({"store": "tea", "date": today, "daysAgo": 0, **duplicate_target})
    with fake_merchant_time(_at(today, 17, 30)):
        _request_json(
            client.post(
                "/merchant/returns/scan",
                headers=merchant_headers["bento"],
                json={"qrValue": duplicate_target["qrValue"]},
            ),
            200,
        )
    with fake_merchant_time(_at(today, 18, 0)):
        duplicate = client.post(
            "/merchant/returns/scan",
            headers=merchant_headers["tea"],
            json={"qrValue": duplicate_target["qrValue"]},
        )
    if duplicate.status_code != 409:
        raise RuntimeError(f"Expected duplicate scan status 409, got {duplicate.status_code}: {duplicate.text}")

    with fake_merchant_time(_at(today, 18, 15)):
        invalid = client.post(
            "/merchant/returns/scan",
            headers=merchant_headers["tea"],
            json={"qrValue": "DEMO-INVALID-QR"},
        )
    if invalid.status_code != 404:
        raise RuntimeError(f"Expected invalid QR status 404, got {invalid.status_code}: {invalid.text}")

    month_query = {"year": str(today.year), "month": str(today.month)}
    monthly_usage = _request_json(
        client.get("/government/web/monthly-usage", headers=government_headers, params=month_query),
        200,
    )
    top_stores = _request_json(
        client.get("/government/web/top-stores", headers=government_headers, params=month_query),
        200,
    )
    merchant_sold = _request_json(
        client.get(
            "/merchant/stats/sold",
            headers=merchant_headers["tea"],
            params={
                "storeId": merchant_store_ids["tea"],
                "from": start_date.isoformat(),
                "to": today.isoformat(),
            },
        ),
        200,
    )

    return {
        "startDate": start_date,
        "endDate": today,
        "createdBatches": len(created_batches),
        "monthlyIssuedCount": monthly_usage["issuedCount"],
        "monthlyReturnedCount": monthly_usage["returnedCount"],
        "topStoreRows": len(top_stores["rankings"]),
        "teaMerchantSold": sum(row["totalCount"] for row in merchant_sold["rows"]),
    }


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_demo_data(db)
        reset_demo_business_data(db)
        rebuild_daily_report_csvs(db)
    finally:
        db.close()

    with TestClient(app) as client:
        result = create_demo_flow(client)

    report_rows = read_report_rows(result["startDate"], result["endDate"])
    sold_rows = [row for row in report_rows if row.get("eventType") == "sold"]
    recovered_rows = [row for row in report_rows if row.get("eventType") == "recovered"]
    report_paths = [daily_report_path(result["startDate"] + timedelta(days=offset)) for offset in range(5)]

    print(f"Generated demo flow from {result['startDate']} to {result['endDate']}.")
    print(f"Created invoice batches through API: {result['createdBatches']}")
    print(f"CSV sold rows: {len(sold_rows)}")
    print(f"CSV recovered rows: {len(recovered_rows)}")
    print(f"Government monthly issued count from API: {result['monthlyIssuedCount']}")
    print(f"Government monthly returned count from API: {result['monthlyReturnedCount']}")
    print(f"Government ranking rows from API: {result['topStoreRows']}")
    print(f"Tea merchant sold count from API: {result['teaMerchantSold']}")
    print("CSV reports:")
    for path in report_paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
