from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
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
            Loan.invoice_sequence == 1,
        )
    )

    qr_value = generate_qr_value(payload.invoice_code, current_user.store.code)
    if loan is None:
        loan = Loan(
            qr_token_hash=hash_qr_value(qr_value),
            issued_store_id=current_user.store_id,
            invoice_code=payload.invoice_code,
            invoice_sequence=1,
            cup_count=payload.cup_count,
            returned_count=0,
            container_type=ContainerType.cup.value,
            deposit_amount=DEPOSIT_AMOUNTS[ContainerType.cup],
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

    return QRCodeResponse(
        loanId=loan.id,
        qrValue=qr_value,
        invoiceCode=payload.invoice_code,
        storeCode=current_user.store.code,
        addedCupCount=payload.cup_count,
        totalCupCount=loan.cup_count,
        returnedCount=loan.returned_count,
        remainingCupCount=loan.cup_count - loan.returned_count,
        depositAmount=loan.deposit_amount,
        totalDepositAmount=loan.cup_count * loan.deposit_amount,
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

    if payload.cup_count > remaining_count:
        db.add(
            ScanEvent(
                qr_token_hash=qr_hash,
                loan_id=loan.id,
                store_id=current_user.store_id,
                result="return_count_exceeded",
                reason="return_count_exceeded",
                note=payload.note,
                created_at=scanned_at,
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Return cup count exceeds remaining count")

    is_expired = scanned_at > loan.due_at
    is_abnormal = payload.condition != ReturnCondition.normal
    refund_amount = loan.deposit_amount * payload.cup_count if not is_expired and not is_abnormal else 0
    refund_reason = _refund_reason(is_expired, payload.condition)
    scan_result = "returned" if refund_amount == loan.deposit_amount * payload.cup_count else "returned_no_refund"

    loan.returned_count += payload.cup_count
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

    return ReturnScanResponse(
        accepted=True,
        loanId=loan.id,
        status=loan.status,
        containerType=loan.container_type,
        invoiceCode=loan.invoice_code,
        issuedStoreId=loan.issued_store_id,
        returnedStoreId=loan.returned_store_id,
        cupCount=payload.cup_count,
        totalCupCount=loan.cup_count,
        returnedCount=loan.returned_count,
        remainingCupCount=loan.cup_count - loan.returned_count,
        depositAmount=loan.deposit_amount,
        refundAmount=refund_amount,
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
    db: Session = Depends(get_db),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantSoldStatsResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    statement = select(Loan).where(
        Loan.issued_store_id == current_user.store_id,
        Loan.issued_at >= from_at,
        Loan.issued_at <= to_at,
    )
    if container_type is not None:
        statement = statement.where(Loan.container_type == container_type.value)
    loans = list(db.scalars(statement))

    return MerchantSoldStatsResponse(
        storeId=current_user.store_id,
        **{"from": from_at, "to": to_at},
        containerType=container_type.value if container_type else None,
        totalCount=sum(loan.cup_count for loan in loans),
        cupCount=sum(loan.cup_count for loan in loans if loan.container_type == ContainerType.cup.value),
        mealBoxCount=sum(loan.cup_count for loan in loans if loan.container_type == ContainerType.meal_box.value),
        depositTotal=sum(loan.deposit_amount * loan.cup_count for loan in loans),
    )


@router.get("/stats/recovered", response_model=MerchantRecoveredStatsResponse)
def get_recovered_stats(
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    db: Session = Depends(get_db),
    current_user: MerchantUser = Depends(get_current_user),
) -> MerchantRecoveredStatsResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    statement = select(Loan).where(
        Loan.returned_store_id == current_user.store_id,
        Loan.returned_at >= from_at,
        Loan.returned_at <= to_at,
    )
    if container_type is not None:
        statement = statement.where(Loan.container_type == container_type.value)
    loans = list(db.scalars(statement))

    normal_count = sum(
        loan.returned_count
        for loan in loans
        if loan.return_condition == ReturnCondition.normal.value and loan.returned_at <= loan.due_at
    )
    expired_count = sum(loan.returned_count for loan in loans if loan.returned_at > loan.due_at)
    abnormal_count = sum(
        loan.returned_count for loan in loans if loan.return_condition and loan.return_condition != ReturnCondition.normal.value
    )
    refund_total = sum(loan.refund_ledger.refund_amount for loan in loans if loan.refund_ledger is not None)

    return MerchantRecoveredStatsResponse(
        storeId=current_user.store_id,
        **{"from": from_at, "to": to_at},
        containerType=container_type.value if container_type else None,
        totalCount=sum(loan.returned_count for loan in loans),
        normalCount=normal_count,
        expiredCount=expired_count,
        abnormalCount=abnormal_count,
        crossStoreCount=sum(loan.returned_count for loan in loans if loan.issued_store_id != loan.returned_store_id),
        refundTotal=refund_total,
    )
