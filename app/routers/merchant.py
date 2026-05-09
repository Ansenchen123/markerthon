from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.daily_reports import append_recovered_report_row, append_sold_report_row, read_report_rows
from app.models import Loan, MerchantUser, RefundLedger, ScanEvent
from app.schemas import (
    ContainerType,
    MerchantRecoveredStatsResponse,
    MerchantSoldStatsResponse,
    QRCodeCreate,
    QRCodeResponse,
    ReturnCondition,
    ReturnScanRequest,
    ReturnScanResponse,
)
from app.security import generate_qr_value, get_current_user, hash_qr_value
from app.time_utils import due_at_from, normalize_taipei, now_taipei


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
    from_at: datetime,
    to_at: datetime,
    container_type: Optional[ContainerType],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_report_rows(from_at.date(), to_at.date()):
        if row.get("eventType") != event_type:
            continue
        if int(row.get("storeId") or 0) != store_id:
            continue
        if container_type is not None and row.get("containerType") != container_type.value:
            continue

        occurred_at = datetime.fromisoformat(row["occurredAt"])
        if from_at <= occurred_at <= to_at:
            rows.append(row)
    return rows


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
                note=payload.note,
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
                note=payload.note,
                created_at=scanned_at,
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This QR value has already been returned")

    is_expired = scanned_at > loan.due_at
    is_abnormal = payload.condition != ReturnCondition.normal
    refund_amount = loan.deposit_amount * return_count if not is_expired and not is_abnormal else 0
    refund_reason = _refund_reason(is_expired, payload.condition)
    scan_result = "returned" if refund_amount == loan.deposit_amount * return_count else "returned_no_refund"

    loan.returned_count += return_count
    loan.status = "returned" if loan.returned_count == loan.cup_count else "partial_returned"
    loan.returned_at = scanned_at
    loan.returned_store_id = current_user.store_id
    loan.return_condition = payload.condition.value
    loan.abnormal_note = payload.note if refund_reason != "normal" else None

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
            note=payload.note,
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
        condition=payload.condition.value,
        result=scan_result,
        reason=None if refund_reason == "normal" else refund_reason,
        is_expired=is_expired,
        is_abnormal=is_abnormal,
        is_cross_store=loan.issued_store_id != current_user.store_id,
        note=payload.note,
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
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantSoldStatsResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    rows = _merchant_report_rows(
        event_type="sold",
        store_id=current_user.store_id,
        from_at=from_at,
        to_at=to_at,
        container_type=container_type,
    )

    return MerchantSoldStatsResponse(
        storeId=current_user.store_id,
        **{"from": from_at, "to": to_at},
        containerType=container_type.value if container_type else None,
        totalCount=sum(_row_count(row) for row in rows),
        cupCount=sum(_row_count(row) for row in rows if row["containerType"] == ContainerType.cup.value),
        mealBoxCount=sum(_row_count(row) for row in rows if row["containerType"] == ContainerType.meal_box.value),
    )


@router.get("/stats/recovered", response_model=MerchantRecoveredStatsResponse)
def get_recovered_stats(
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantRecoveredStatsResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    rows = _merchant_report_rows(
        event_type="recovered",
        store_id=current_user.store_id,
        from_at=from_at,
        to_at=to_at,
        container_type=container_type,
    )

    return MerchantRecoveredStatsResponse(
        storeId=current_user.store_id,
        **{"from": from_at, "to": to_at},
        containerType=container_type.value if container_type else None,
        totalCount=sum(_row_count(row) for row in rows),
        normalCount=sum(
            _row_count(row) for row in rows if not _row_bool(row, "isExpired") and not _row_bool(row, "isAbnormal")
        ),
        expiredCount=sum(_row_count(row) for row in rows if _row_bool(row, "isExpired")),
        abnormalCount=sum(_row_count(row) for row in rows if _row_bool(row, "isAbnormal")),
        crossStoreCount=sum(_row_count(row) for row in rows if _row_bool(row, "isCrossStore")),
    )
