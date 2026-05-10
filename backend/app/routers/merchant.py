from datetime import date, datetime, time, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.daily_reports import append_recovered_report_row, append_sold_report_row, iter_report_dates, read_report_rows
from app.models import Loan, MerchantUser, RefundLedger, ScanEvent
from app.schemas import (
    CategoryLabel,
    CategoryCount,
    MerchantRecoveredStatsRow,
    MerchantRecoveredStatsResponse,
    MerchantSoldStatsRow,
    MerchantSoldStatsResponse,
    MerchantStoreRegionRequest,
    QRCodeCreate,
    QRCodeResponse,
    ReturnCondition,
    ReturnScanRequest,
    ReturnScanResponse,
    StoreResponse,
)
from app.security import generate_qr_value, get_current_user, hash_qr_value
from app.time_utils import due_at_from, now_taipei


router = APIRouter(prefix="/merchant", tags=["merchant"])

DEPOSIT_AMOUNTS = {
    CategoryLabel.cup: 20,
    CategoryLabel.meal_box: 50,
}


def _remaining(loan: Loan) -> int:
    if loan.remaining_count is None:
        return max(loan.item_count - loan.returned_count, 0)
    return max(loan.remaining_count, 0)


def _refund_reason(is_expired: bool, condition: ReturnCondition) -> str:
    reasons: list[str] = []
    if is_expired:
        reasons.append("expired")
    if condition != ReturnCondition.normal:
        reasons.append(condition.value)
    return ",".join(reasons) if reasons else "normal"


def _ensure_store_scope(store_id: int, current_user: MerchantUser) -> None:
    if store_id != current_user.store_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Store is not allowed for this merchant")


def _row_count(row: dict[str, str]) -> int:
    return int(row.get("count") or 0)


def _row_category(row: dict[str, str]) -> str:
    return row.get("category") or ""


def _row_bool(row: dict[str, str], key: str) -> bool:
    return (row.get(key) or "").strip().lower() == "true"


def _date_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    return datetime.combine(from_date, time.min), datetime.combine(to_date + timedelta(days=1), time.min)


@router.patch("/store/region", response_model=StoreResponse)
def update_store_region(
    payload: MerchantStoreRegionRequest,
    current_user: MerchantUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreResponse:
    store = current_user.store
    store.region = payload.region
    db.add(store)
    db.commit()
    db.refresh(store)
    return StoreResponse(id=store.id, code=store.code, name=store.name, region=store.region)


def _remaining_for_issued_between(db: Session, *, store_id: int, from_date: date, to_date: date) -> int:
    start_at, end_at = _date_bounds(from_date, to_date)
    loans = db.scalars(
        select(Loan).where(
            Loan.issued_store_id == store_id,
            Loan.issued_at >= start_at,
            Loan.issued_at < end_at,
        )
    )
    return sum(_remaining(loan) for loan in loans)


def _merchant_report_rows(
    *,
    event_type: str,
    store_id: int,
    from_date: date,
    to_date: date,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_report_rows(from_date, to_date):
        if row.get("eventType") != event_type:
            continue
        if int(row.get("storeId") or 0) != store_id:
            continue

        occurred_date = datetime.fromisoformat(row["occurredAt"]).date()
        if from_date <= occurred_date <= to_date:
            rows.append(row)
    return rows


def _sold_stat_rows(
    *,
    rows: list[dict[str, str]],
    from_date: date,
    to_date: date,
) -> list[MerchantSoldStatsRow]:
    summaries = {
        stat_date: {"totalCount": 0, "categoryCounts": {category.value: 0 for category in CategoryLabel}}
        for stat_date in iter_report_dates(from_date, to_date)
    }
    for row in rows:
        stat_date = datetime.fromisoformat(row["occurredAt"]).date()
        count = _row_count(row)
        summaries[stat_date]["totalCount"] += count
        category = _row_category(row)
        summaries[stat_date]["categoryCounts"][category] = summaries[stat_date]["categoryCounts"].get(category, 0) + count

    return [
        MerchantSoldStatsRow(
            statDate=stat_date,
            totalCount=summary["totalCount"],
            categoryCounts=[
                CategoryCount(category=category, count=count)
                for category, count in sorted(summary["categoryCounts"].items())
            ],
        )
        for stat_date, summary in summaries.items()
    ]


def _recovered_stat_rows(
    *,
    rows: list[dict[str, str]],
    from_date: date,
    to_date: date,
) -> list[MerchantRecoveredStatsRow]:
    summaries = {
        stat_date: {
            "totalCount": 0,
            "categoryCounts": {category.value: 0 for category in CategoryLabel},
            "normalCount": 0,
            "expiredCount": 0,
            "abnormalCount": 0,
            "crossStoreCount": 0,
        }
        for stat_date in iter_report_dates(from_date, to_date)
    }
    for row in rows:
        stat_date = datetime.fromisoformat(row["occurredAt"]).date()
        count = _row_count(row)
        summaries[stat_date]["totalCount"] += count
        category = _row_category(row)
        summaries[stat_date]["categoryCounts"][category] = summaries[stat_date]["categoryCounts"].get(category, 0) + count
        summaries[stat_date]["normalCount"] += (
            count if not _row_bool(row, "isExpired") and not _row_bool(row, "isAbnormal") else 0
        )
        summaries[stat_date]["expiredCount"] += count if _row_bool(row, "isExpired") else 0
        summaries[stat_date]["abnormalCount"] += count if _row_bool(row, "isAbnormal") else 0
        summaries[stat_date]["crossStoreCount"] += count if _row_bool(row, "isCrossStore") else 0

    return [
        MerchantRecoveredStatsRow(
            statDate=stat_date,
            totalCount=summary["totalCount"],
            categoryCounts=[
                CategoryCount(category=category, count=count)
                for category, count in sorted(summary["categoryCounts"].items())
            ],
            normalCount=summary["normalCount"],
            expiredCount=summary["expiredCount"],
            abnormalCount=summary["abnormalCount"],
            crossStoreCount=summary["crossStoreCount"],
        )
        for stat_date, summary in summaries.items()
    ]


@router.post("/qr-codes", response_model=QRCodeResponse, status_code=status.HTTP_201_CREATED)
def create_qr_code(
    payload: QRCodeCreate,
    db: Session = Depends(get_db),
    current_user: MerchantUser = Depends(get_current_user),
) -> QRCodeResponse:
    issued_at = now_taipei()
    loan = db.scalar(
        select(Loan).where(
            Loan.issued_store_id == current_user.store_id,
            Loan.invoice_code == payload.invoice_code,
            Loan.container_type == payload.category.value,
            Loan.invoice_sequence == 1,
        )
    )

    qr_value = generate_qr_value(payload.invoice_code, current_user.store.code, payload.category.value)
    if loan is None:
        loan = Loan(
            qr_token_hash=hash_qr_value(qr_value),
            issued_store_id=current_user.store_id,
            invoice_code=payload.invoice_code,
            invoice_sequence=1,
            item_count=payload.count,
            returned_count=0,
            remaining_count=payload.count,
            container_type=payload.category.value,
            deposit_amount=DEPOSIT_AMOUNTS[payload.category],
            status="active",
            issued_at=issued_at,
            due_at=due_at_from(issued_at),
        )
        db.add(loan)
    else:
        current_remaining = _remaining(loan)
        loan.qr_token_hash = hash_qr_value(qr_value)
        loan.item_count += payload.count
        loan.remaining_count = current_remaining + payload.count
        if loan.status == "returned":
            loan.status = "partial_returned"

    db.commit()
    db.refresh(loan)
    append_sold_report_row(
        loan=loan,
        qr_value=qr_value,
        added_count=payload.count,
        occurred_at=issued_at,
    )

    return QRCodeResponse(
        loanId=loan.id,
        qrValue=qr_value,
        invoiceCode=payload.invoice_code,
        storeCode=current_user.store.code,
        category=loan.container_type,
        addedCount=payload.count,
        totalCount=loan.item_count,
        returnedCount=loan.returned_count,
        remainingCount=_remaining(loan),
        issuedAt=loan.issued_at,
        dueAt=loan.due_at,
    )


@router.post(
    "/returns/scan",
    response_model=ReturnScanResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "QR Code 無法辨識"},
        status.HTTP_409_CONFLICT: {"description": "這張 QR Code 已全數歸還"},
    },
)
def scan_return(
    payload: ReturnScanRequest,
    db: Session = Depends(get_db),
    current_user: MerchantUser = Depends(get_current_user),
) -> ReturnScanResponse:
    scanned_at = now_taipei()
    return_count = 1
    qr_hash = hash_qr_value(payload.qr_value)
    loan = db.scalar(select(Loan).where(Loan.qr_token_hash == qr_hash))

    if loan is None:
        db.add(
            ScanEvent(
                qr_token_hash=qr_hash,
                store_id=current_user.store_id,
                result="invalid_qr",
                reason="invalid_qr",
                note=None,
                created_at=scanned_at,
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR Code 無法辨識")

    remaining_count = _remaining(loan)
    if remaining_count <= 0 or loan.status == "returned":
        db.add(
            ScanEvent(
                qr_token_hash=qr_hash,
                loan_id=loan.id,
                store_id=current_user.store_id,
                result="duplicate_scan",
                reason="already_returned",
                note=None,
                created_at=scanned_at,
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="這張 QR Code 已全數歸還")

    condition = ReturnCondition.normal
    note = None
    is_expired = scanned_at > loan.due_at
    is_abnormal = False
    refund_amount = loan.deposit_amount * return_count if not is_expired and not is_abnormal else 0
    refund_reason = _refund_reason(is_expired, condition)
    scan_result = "returned" if refund_amount == loan.deposit_amount * return_count else "returned_no_refund"

    loan.returned_count += return_count
    loan.remaining_count = max(remaining_count - return_count, 0)
    loan.status = "returned" if loan.remaining_count == 0 else "partial_returned"
    loan.returned_at = scanned_at
    loan.returned_store_id = current_user.store_id
    loan.return_condition = condition.value
    loan.abnormal_note = None

    refund_ledger = loan.refund_ledger
    if refund_ledger is None:
        refund_ledger = RefundLedger(
            loan_id=loan.id,
            store_id=current_user.store_id,
            refund_amount=0,
            reason=refund_reason,
            created_at=scanned_at,
        )
        db.add(refund_ledger)

    refund_ledger.store_id = current_user.store_id
    refund_ledger.refund_amount += refund_amount
    refund_ledger.reason = refund_reason
    refund_ledger.created_at = scanned_at

    db.add(
        ScanEvent(
            qr_token_hash=qr_hash,
            loan_id=loan.id,
            store_id=current_user.store_id,
            result=scan_result,
            reason=None if refund_reason == "normal" else refund_reason,
            note=note,
            created_at=scanned_at,
        )
    )
    db.commit()
    db.refresh(loan)
    append_recovered_report_row(
        loan=loan,
        qr_value=payload.qr_value,
        recovered_store_id=current_user.store_id,
        recovered_store_code=current_user.store.code,
        recovered_store_name=current_user.store.name,
        count=return_count,
        condition=condition.value,
        result=scan_result,
        reason=None if refund_reason == "normal" else refund_reason,
        is_expired=is_expired,
        is_abnormal=is_abnormal,
        is_cross_store=loan.issued_store_id != current_user.store_id,
        note=note,
        occurred_at=scanned_at,
    )

    return ReturnScanResponse(
        accepted=True,
        loanId=loan.id,
        status=loan.status,
        category=loan.container_type,
        invoiceCode=loan.invoice_code,
        issuedStoreId=loan.issued_store_id,
        returnedStoreId=loan.returned_store_id,
        count=return_count,
        totalCount=loan.item_count,
        returnedCount=loan.returned_count,
        remainingCount=_remaining(loan),
        refundReason=refund_reason,
        isExpired=is_expired,
        isAbnormal=is_abnormal,
        dueAt=loan.due_at,
        returnedAt=loan.returned_at,
    )


@router.get(
    "/stats/sold",
    response_model=MerchantSoldStatsResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "from must be before or equal to to"},
        status.HTTP_403_FORBIDDEN: {"description": "Store is not allowed for this merchant"},
    },
)
def get_sold_stats(
    store_id: int = Query(..., alias="storeId", gt=0),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantSoldStatsResponse:
    _ensure_store_scope(store_id, current_user)
    if from_date > to_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before or equal to to")
    rows = _merchant_report_rows(
        event_type="sold",
        store_id=current_user.store_id,
        from_date=from_date,
        to_date=to_date,
    )
    remaining_count = _remaining_for_issued_between(
        db,
        store_id=current_user.store_id,
        from_date=from_date,
        to_date=to_date,
    )

    return MerchantSoldStatsResponse(
        storeId=current_user.store_id,
        storeName=current_user.store.name,
        **{"from": from_date, "to": to_date},
        remainingCount=remaining_count,
        rows=_sold_stat_rows(
            rows=rows,
            from_date=from_date,
            to_date=to_date,
        ),
    )


@router.get(
    "/stats/recovered",
    response_model=MerchantRecoveredStatsResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "from must be before or equal to to"},
        status.HTTP_403_FORBIDDEN: {"description": "Store is not allowed for this merchant"},
    },
)
def get_recovered_stats(
    store_id: int = Query(..., alias="storeId", gt=0),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantRecoveredStatsResponse:
    _ensure_store_scope(store_id, current_user)
    if from_date > to_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before or equal to to")
    rows = _merchant_report_rows(
        event_type="recovered",
        store_id=current_user.store_id,
        from_date=from_date,
        to_date=to_date,
    )

    return MerchantRecoveredStatsResponse(
        storeId=current_user.store_id,
        storeName=current_user.store.name,
        **{"from": from_date, "to": to_date},
        rows=_recovered_stat_rows(rows=rows, from_date=from_date, to_date=to_date),
    )
