from __future__ import annotations

import csv
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Loan, ScanEvent
from app.security import generate_qr_value


REPORT_COLUMNS = [
    "eventType",
    "occurredAt",
    "loanId",
    "invoiceCode",
    "qrValue",
    "storeId",
    "storeCode",
    "storeName",
    "issuedStoreId",
    "issuedStoreCode",
    "issuedStoreName",
    "returnedStoreId",
    "returnedStoreCode",
    "returnedStoreName",
    "category",
    "count",
    "totalCount",
    "returnedCount",
    "remainingCount",
    "condition",
    "result",
    "reason",
    "isExpired",
    "isAbnormal",
    "isCrossStore",
    "note",
]


def report_dir() -> Path:
    return Path(os.getenv("DAILY_REPORT_DIR", settings.daily_report_dir))


def daily_report_path(stat_date: date) -> Path:
    return report_dir() / f"daily_report_{stat_date.isoformat()}.csv"


def _format_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _remaining(loan: Loan) -> int:
    if loan.remaining_count is None:
        return max(loan.item_count - loan.returned_count, 0)
    return max(loan.remaining_count, 0)


def _append_report_row(occurred_at: datetime, row: dict[str, object]) -> None:
    path = daily_report_path(occurred_at.date())
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0

    output = {column: "" for column in REPORT_COLUMNS}
    output.update({key: value for key, value in row.items() if key in output})
    for key, value in output.items():
        if isinstance(value, bool):
            output[key] = _format_bool(value)
        elif isinstance(value, datetime):
            output[key] = value.isoformat()
        elif value is None:
            output[key] = ""
        else:
            output[key] = str(value)

    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REPORT_COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(output)


def append_sold_report_row(*, loan: Loan, qr_value: str, added_count: int, occurred_at: datetime) -> None:
    _append_report_row(
        occurred_at,
        {
            "eventType": "sold",
            "occurredAt": occurred_at,
            "loanId": loan.id,
            "invoiceCode": loan.invoice_code,
            "qrValue": qr_value,
            "storeId": loan.issued_store_id,
            "storeCode": loan.issued_store.code,
            "storeName": loan.issued_store.name,
            "issuedStoreId": loan.issued_store_id,
            "issuedStoreCode": loan.issued_store.code,
            "issuedStoreName": loan.issued_store.name,
            "category": loan.container_type,
            "count": added_count,
            "totalCount": loan.item_count,
            "returnedCount": loan.returned_count,
            "remainingCount": _remaining(loan),
        },
    )


def append_recovered_report_row(
    *,
    loan: Loan,
    qr_value: str,
    recovered_store_id: int,
    recovered_store_code: str,
    recovered_store_name: str,
    count: int,
    condition: str,
    result: str,
    reason: str | None,
    is_expired: bool,
    is_abnormal: bool,
    is_cross_store: bool,
    note: str | None,
    occurred_at: datetime,
) -> None:
    _append_report_row(
        occurred_at,
        {
            "eventType": "recovered",
            "occurredAt": occurred_at,
            "loanId": loan.id,
            "invoiceCode": loan.invoice_code,
            "qrValue": qr_value,
            "storeId": recovered_store_id,
            "storeCode": recovered_store_code,
            "storeName": recovered_store_name,
            "issuedStoreId": loan.issued_store_id,
            "issuedStoreCode": loan.issued_store.code,
            "issuedStoreName": loan.issued_store.name,
            "returnedStoreId": recovered_store_id,
            "returnedStoreCode": recovered_store_code,
            "returnedStoreName": recovered_store_name,
            "category": loan.container_type,
            "count": count,
            "totalCount": loan.item_count,
            "returnedCount": loan.returned_count,
            "remainingCount": _remaining(loan),
            "condition": condition,
            "result": result,
            "reason": reason,
            "isExpired": is_expired,
            "isAbnormal": is_abnormal,
            "isCrossStore": is_cross_store,
            "note": note,
        },
    )


def iter_report_dates(from_date: date, to_date: date) -> Iterable[date]:
    current = from_date
    while current <= to_date:
        yield current
        current += timedelta(days=1)


def read_report_rows(from_date: date, to_date: date) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for stat_date in iter_report_dates(from_date, to_date):
        path = daily_report_path(stat_date)
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as file:
            rows.extend(csv.DictReader(file))
    return rows


def rebuild_daily_report_csvs(db: Session) -> None:
    directory = report_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("daily_report_*.csv"):
        path.unlink()

    for loan in db.scalars(select(Loan).order_by(Loan.issued_at, Loan.id)):
        append_sold_report_row(
            loan=loan,
            qr_value=generate_qr_value(loan.invoice_code, loan.issued_store.code, loan.container_type),
            added_count=loan.item_count,
            occurred_at=loan.issued_at,
        )

    events = db.scalars(
        select(ScanEvent)
        .where(ScanEvent.result.in_(("returned", "returned_no_refund")))
        .order_by(ScanEvent.created_at, ScanEvent.id)
    )
    for event in events:
        if event.loan is None:
            continue
        is_expired = event.created_at > event.loan.due_at
        is_abnormal = bool(event.reason and event.reason != "expired")
        append_recovered_report_row(
            loan=event.loan,
            qr_value=generate_qr_value(
                event.loan.invoice_code,
                event.loan.issued_store.code,
                event.loan.container_type,
            ),
            recovered_store_id=event.store_id,
            recovered_store_code=event.store.code,
            recovered_store_name=event.store.name,
            count=1,
            condition=event.loan.return_condition or "normal",
            result=event.result,
            reason=event.reason,
            is_expired=is_expired,
            is_abnormal=is_abnormal,
            is_cross_store=event.loan.issued_store_id != event.store_id,
            note=event.note,
            occurred_at=event.created_at,
        )
