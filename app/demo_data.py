from contextlib import contextmanager
from datetime import datetime, time, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.routers.merchant as merchant_router
from app.daily_reports import daily_report_path, rebuild_daily_report_csvs, read_daily_recovered_summary, read_daily_sold_summary
from app.database import SessionLocal
from app.init_db import init_db
from app.main import app
from app.models import Loan, RefundLedger, ScanEvent
from app.seed import seed_demo_data
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
DEMO_PASSWORD = "password123"
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
    merchant_headers = {key: _login(client, email) for key, email in MERCHANT_EMAILS.items()}
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
            cup_count = sales_counts[day_index % len(sales_counts)][store_key]
            invoice_code = f"{DEMO_INVOICE_PREFIX}{order_date.strftime('%Y%m%d')}-{STORE_CODES[store_key].upper()}-01"
            issue_time = _at(order_date, 9 + store_index, 15)

            with fake_merchant_time(issue_time):
                batch = _request_json(
                    client.post(
                        "/merchant/qr-codes",
                        headers=merchant_headers[store_key],
                        json={"invoiceCode": invoice_code, "cupCount": cup_count},
                    ),
                    201,
                )
            created_batches.append({"store": store_key, "date": order_date, "daysAgo": days_ago, **batch})

            if days_ago >= 3:
                planned_returns = cup_count - 1
            elif days_ago >= 1:
                planned_returns = max(cup_count - 2, 1)
            else:
                planned_returns = min(cup_count, 1)

            for scan_index in range(planned_returns):
                if days_ago >= 4 and scan_index == planned_returns - 1:
                    return_date = today
                    return_hour = 16
                else:
                    return_date = min(order_date + timedelta(days=1), today)
                    return_hour = 12 + scan_index

                receiver_key = STORE_ORDER[(store_index + scan_index + 1) % len(STORE_ORDER)]
                condition = "normal"
                note = None
                if day_index == 1 and store_key == "bento" and scan_index == 0:
                    condition = "polluted"
                    note = "demo: cup has coffee residue"
                elif day_index == 2 and store_key == "cafe" and scan_index == 0:
                    condition = "damaged"
                    note = "demo: lid cracked"

                with fake_merchant_time(_at(return_date, return_hour, 30)):
                    _request_json(
                        client.post(
                            "/merchant/returns/scan",
                            headers=merchant_headers[receiver_key],
                            json={"qrValue": batch["qrValue"], "condition": condition, "note": note},
                        ),
                        200,
                    )

    duplicate_invoice = f"{DEMO_INVOICE_PREFIX}{today.strftime('%Y%m%d')}-DUPLICATE-CHECK"
    with fake_merchant_time(_at(today, 17, 0)):
        duplicate_target = _request_json(
            client.post(
                "/merchant/qr-codes",
                headers=merchant_headers["tea"],
                json={"invoiceCode": duplicate_invoice, "cupCount": 1},
            ),
            201,
        )
    created_batches.append({"store": "tea", "date": today, "daysAgo": 0, **duplicate_target})
    with fake_merchant_time(_at(today, 17, 30)):
        _request_json(
            client.post(
                "/merchant/returns/scan",
                headers=merchant_headers["bento"],
                json={"qrValue": duplicate_target["qrValue"], "condition": "normal"},
            ),
            200,
        )
    with fake_merchant_time(_at(today, 18, 0)):
        duplicate = client.post(
            "/merchant/returns/scan",
            headers=merchant_headers["tea"],
            json={"qrValue": duplicate_target["qrValue"], "condition": "normal"},
        )
    if duplicate.status_code != 409:
        raise RuntimeError(f"Expected duplicate scan status 409, got {duplicate.status_code}: {duplicate.text}")

    with fake_merchant_time(_at(today, 18, 15)):
        invalid = client.post(
            "/merchant/returns/scan",
            headers=merchant_headers["tea"],
            json={"qrValue": "DEMO-INVALID-QR", "condition": "normal"},
        )
    if invalid.status_code != 404:
        raise RuntimeError(f"Expected invalid QR status 404, got {invalid.status_code}: {invalid.text}")

    from_param = start_date.isoformat()
    to_param = today.isoformat()
    sold = _request_json(
        client.get("/government/daily/sold", headers=government_headers, params={"from": from_param, "to": to_param}),
        200,
    )
    recovered = _request_json(
        client.get("/government/daily/recovered", headers=government_headers, params={"from": from_param, "to": to_param}),
        200,
    )
    merchant_sold = _request_json(
        client.get(
            "/merchant/stats/sold",
            headers=merchant_headers["tea"],
            params={
                "from": datetime.combine(start_date, time.min).isoformat(),
                "to": datetime.combine(today, time.max).isoformat(),
            },
        ),
        200,
    )

    return {
        "startDate": start_date,
        "endDate": today,
        "createdBatches": len(created_batches),
        "soldRows": sold["rows"],
        "recoveredRows": recovered["rows"],
        "teaMerchantSold": merchant_sold["totalCount"],
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

    sold_summary = read_daily_sold_summary(result["startDate"], result["endDate"])
    recovered_summary = read_daily_recovered_summary(result["startDate"], result["endDate"])
    report_paths = [daily_report_path(result["startDate"] + timedelta(days=offset)) for offset in range(5)]

    print(f"Generated demo flow from {result['startDate']} to {result['endDate']}.")
    print(f"Created invoice batches through API: {result['createdBatches']}")
    print(f"Daily sold summary rows: {len(sold_summary)}")
    print(f"Daily recovered summary rows: {len(recovered_summary)}")
    print(f"Tea merchant sold count from API: {result['teaMerchantSold']}")
    print("CSV reports:")
    for path in report_paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
