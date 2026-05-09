from datetime import datetime
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DailyRecoveredStats, DailySoldStats, Loan, ScanEvent


def record_daily_sold(db: Session, *, store_id: int, container_type: str, count: int, occurred_at: datetime) -> None:
    row = db.scalar(
        select(DailySoldStats).where(
            DailySoldStats.stat_date == occurred_at.date(),
            DailySoldStats.store_id == store_id,
            DailySoldStats.container_type == container_type,
        )
    )
    if row is None:
        row = DailySoldStats(
            stat_date=occurred_at.date(),
            store_id=store_id,
            container_type=container_type,
            sold_count=0,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        db.add(row)

    row.sold_count += count
    row.updated_at = occurred_at


def record_daily_recovered(
    db: Session,
    *,
    store_id: int,
    container_type: str,
    count: int,
    is_normal: bool,
    is_expired: bool,
    is_abnormal: bool,
    is_cross_store: bool,
    occurred_at: datetime,
) -> None:
    row = db.scalar(
        select(DailyRecoveredStats).where(
            DailyRecoveredStats.stat_date == occurred_at.date(),
            DailyRecoveredStats.store_id == store_id,
            DailyRecoveredStats.container_type == container_type,
        )
    )
    if row is None:
        row = DailyRecoveredStats(
            stat_date=occurred_at.date(),
            store_id=store_id,
            container_type=container_type,
            recovered_count=0,
            normal_count=0,
            expired_count=0,
            abnormal_count=0,
            cross_store_count=0,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        db.add(row)

    row.recovered_count += count
    row.normal_count += count if is_normal else 0
    row.expired_count += count if is_expired else 0
    row.abnormal_count += count if is_abnormal else 0
    row.cross_store_count += count if is_cross_store else 0
    row.updated_at = occurred_at


def rebuild_daily_stats(db: Session) -> None:
    db.execute(delete(DailySoldStats))
    db.execute(delete(DailyRecoveredStats))
    db.flush()

    sold_rows: dict[tuple, dict] = {}
    for loan in db.scalars(select(Loan)):
        key = (loan.issued_at.date(), loan.issued_store_id, loan.container_type)
        row = sold_rows.setdefault(
            key,
            {
                "sold_count": 0,
                "created_at": loan.issued_at,
                "updated_at": loan.issued_at,
            },
        )
        row["sold_count"] += loan.cup_count
        row["created_at"] = min(row["created_at"], loan.issued_at)
        row["updated_at"] = max(row["updated_at"], loan.issued_at)

    for (stat_date, store_id, container_type), values in sold_rows.items():
        db.add(
            DailySoldStats(
                stat_date=stat_date,
                store_id=store_id,
                container_type=container_type,
                sold_count=values["sold_count"],
                created_at=values["created_at"],
                updated_at=values["updated_at"],
            )
        )

    recovered_rows = defaultdict(
        lambda: {
            "recovered_count": 0,
            "normal_count": 0,
            "expired_count": 0,
            "abnormal_count": 0,
            "cross_store_count": 0,
            "created_at": None,
            "updated_at": None,
        }
    )
    events = db.scalars(select(ScanEvent).where(ScanEvent.result.in_(("returned", "returned_no_refund"))))
    for event in events:
        if event.loan is None:
            continue
        is_expired = event.created_at > event.loan.due_at
        is_abnormal = bool(event.reason and event.reason != "expired")
        key = (event.created_at.date(), event.store_id, event.loan.container_type)
        row = recovered_rows[key]
        row["recovered_count"] += 1
        row["normal_count"] += 1 if not is_expired and not is_abnormal else 0
        row["expired_count"] += 1 if is_expired else 0
        row["abnormal_count"] += 1 if is_abnormal else 0
        row["cross_store_count"] += 1 if event.loan.issued_store_id != event.store_id else 0
        row["created_at"] = event.created_at if row["created_at"] is None else min(row["created_at"], event.created_at)
        row["updated_at"] = event.created_at if row["updated_at"] is None else max(row["updated_at"], event.created_at)

    for (stat_date, store_id, container_type), values in recovered_rows.items():
        db.add(
            DailyRecoveredStats(
                stat_date=stat_date,
                store_id=store_id,
                container_type=container_type,
                recovered_count=values["recovered_count"],
                normal_count=values["normal_count"],
                expired_count=values["expired_count"],
                abnormal_count=values["abnormal_count"],
                cross_store_count=values["cross_store_count"],
                created_at=values["created_at"],
                updated_at=values["updated_at"],
            )
        )

    db.commit()
