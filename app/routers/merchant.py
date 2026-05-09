from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.daily_reports import append_recovered_report_row, append_sold_report_row, iter_report_dates, read_report_rows
from app.models import Loan, MerchantUser, RefundLedger, ScanEvent
from app.schemas import (
    ContainerType,
    MerchantRecoveredStatsRow,
    MerchantRecoveredStatsResponse,
    MerchantSoldStatsRow,
    MerchantSoldStatsResponse,
    QRCodeCreate,
    QRCodeResponse,
    ReturnCondition,
    ReturnScanRequest,
    ReturnScanResponse,
)
from app.security import generate_qr_value, get_current_user, hash_qr_value
from app.time_utils import due_at_from, now_taipei


router = APIRouter(prefix="/merchant", tags=["merchant"])

DEPOSIT_AMOUNTS = {
    ContainerType.cup: 20,
    ContainerType.meal_box: 50,
}


def _refund_reason(is_expired: bool, condition: ReturnCondition) -> str:
    reasons: list[str] = []
    if is_expired:
        reasons.append("expired")
    if condition != ReturnCondition.normal:
        reasons.append(condition.value)
    return ",".join(reasons) if reasons else "normal"


def _row_count(row: dict[str, str]) -> int:
    return int(row.get("cupCount") or 0)


def _row_bool(row: dict[str, str], key: str) -> bool:
    return (row.get(key) or "").strip().lower() == "true"


def _merchant_report_rows(
    *,
    event_type: str,
    store_id: int,
    from_date: date,
    to_date: date,
    container_type: Optional[ContainerType],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_report_rows(from_date, to_date):
        if row.get("eventType") != event_type:
            continue
        if int(row.get("storeId") or 0) != store_id:
            continue
        if container_type is not None and row.get("containerType") != container_type.value:
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
        stat_date: {"totalCount": 0, "cupCount": 0, "mealBoxCount": 0}
        for stat_date in iter_report_dates(from_date, to_date)
    }
    for row in rows:
        stat_date = datetime.fromisoformat(row["occurredAt"]).date()
        count = _row_count(row)
        summaries[stat_date]["totalCount"] += count
        if row["containerType"] == ContainerType.cup.value:
            summaries[stat_date]["cupCount"] += count
        elif row["containerType"] == ContainerType.meal_box.value:
            summaries[stat_date]["mealBoxCount"] += count

    return [
        MerchantSoldStatsRow(
            statDate=stat_date,
            totalCount=summary["totalCount"],
            cupCount=summary["cupCount"],
            mealBoxCount=summary["mealBoxCount"],
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
        stat_date: {"totalCount": 0, "normalCount": 0, "expiredCount": 0, "abnormalCount": 0, "crossStoreCount": 0}
        for stat_date in iter_report_dates(from_date, to_date)
    }
    for row in rows:
        stat_date = datetime.fromisoformat(row["occurredAt"]).date()
        count = _row_count(row)
        summaries[stat_date]["totalCount"] += count
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
            Loan.container_type == payload.container_type.value,
            Loan.invoice_sequence == 1,
        )
    )

    qr_value = generate_qr_value(payload.invoice_code, current_user.store.code, payload.container_type.value)
    if loan is None:
        loan = Loan(
            qr_token_hash=hash_qr_value(qr_value),
            issued_store_id=current_user.store_id,
            invoice_code=payload.invoice_code,
            invoice_sequence=1,
            cup_count=payload.cup_count,
            returned_count=0,
            container_type=payload.container_type.value,
            deposit_amount=DEPOSIT_AMOUNTS[payload.container_type],
            status="active",
            issued_at=issued_at,
            due_at=due_at_from(issued_at),
        )
        db.add(loan)
    else:
        loan.qr_token_hash = hash_qr_value(qr_value)
        loan.cup_count += payload.cup_count
        if loan.status == "returned":
            loan.status = "partial_returned"

    db.commit()
    db.refresh(loan)
    append_sold_report_row(
        loan=loan,
        qr_value=qr_value,
        added_count=payload.cup_count,
        occurred_at=issued_at,
    )

    return QRCodeResponse(
        loanId=loan.id,
        qrValue=qr_value,
        invoiceCode=payload.invoice_code,
        storeCode=current_user.store.code,
        containerType=loan.container_type,
        addedCupCount=payload.cup_count,
        totalCupCount=loan.cup_count,
        returnedCount=loan.returned_count,
        remainingCupCount=loan.cup_count - loan.returned_count,
        issuedAt=loan.issued_at,
        dueAt=loan.due_at,
    )


@router.post("/returns/scan", response_model=ReturnScanResponse)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR value is not recognized")

    remaining_count = loan.cup_count - loan.returned_count
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This QR value has already been returned")

    condition = ReturnCondition.normal
    note = None
    is_expired = scanned_at > loan.due_at
    is_abnormal = False
    refund_amount = loan.deposit_amount * return_count if not is_expired and not is_abnormal else 0
    refund_reason = _refund_reason(is_expired, condition)
    scan_result = "returned" if refund_amount == loan.deposit_amount * return_count else "returned_no_refund"

    loan.returned_count += return_count
    loan.status = "returned" if loan.returned_count == loan.cup_count else "partial_returned"
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
        containerType=loan.container_type,
        invoiceCode=loan.invoice_code,
        issuedStoreId=loan.issued_store_id,
        returnedStoreId=loan.returned_store_id,
        cupCount=return_count,
        totalCupCount=loan.cup_count,
        returnedCount=loan.returned_count,
        remainingCupCount=loan.cup_count - loan.returned_count,
        refundReason=refund_reason,
        isExpired=is_expired,
        isAbnormal=is_abnormal,
        dueAt=loan.due_at,
        returnedAt=loan.returned_at,
    )


@router.get("/stats/sold", response_model=MerchantSoldStatsResponse)
def get_sold_stats(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantSoldStatsResponse:
    if from_date > to_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before or equal to to")
    rows = _merchant_report_rows(
        event_type="sold",
        store_id=current_user.store_id,
        from_date=from_date,
        to_date=to_date,
        container_type=container_type,
    )

    return MerchantSoldStatsResponse(
        storeId=current_user.store_id,
        **{"from": from_date, "to": to_date},
        containerType=container_type.value if container_type else None,
        rows=_sold_stat_rows(rows=rows, from_date=from_date, to_date=to_date),
    )


@router.get("/stats/recovered", response_model=MerchantRecoveredStatsResponse)
def get_recovered_stats(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantRecoveredStatsResponse:
    if from_date > to_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before or equal to to")
    rows = _merchant_report_rows(
        event_type="recovered",
        store_id=current_user.store_id,
        from_date=from_date,
        to_date=to_date,
        container_type=container_type,
    )

    return MerchantRecoveredStatsResponse(
        storeId=current_user.store_id,
        **{"from": from_date, "to": to_date},
        containerType=container_type.value if container_type else None,
        rows=_recovered_stat_rows(rows=rows, from_date=from_date, to_date=to_date),
    )
