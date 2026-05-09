from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.daily_reports import read_daily_recovered_summary, read_daily_sold_summary
from app.database import get_db
from app.models import GovernmentUser, Loan, ScanEvent, Store
from app.schemas import (
    ContainerType,
    GovernmentAnomaliesResponse,
    GovernmentAnomalyResponse,
    GovernmentDailyRecoveredStatsResponse,
    GovernmentDailyRecoveredStatsRow,
    GovernmentDailySoldStatsResponse,
    GovernmentDailySoldStatsRow,
    GovernmentInvoiceDetailResponse,
    GovernmentInvoicesResponse,
    GovernmentInvoiceSummary,
    GovernmentLoginResponse,
    GovernmentOverviewResponse,
    GovernmentRegisterRequest,
    GovernmentScanEventResponse,
    GovernmentStoresResponse,
    GovernmentStoreStatsResponse,
    GovernmentUserResponse,
    LoginRequest,
)
from app.security import create_access_token, generate_qr_value, get_current_government_user, hash_password, verify_password
from app.time_utils import normalize_taipei, now_taipei


router = APIRouter(prefix="/government", tags=["government"])


def _rate(returned_count: int, issued_count: int) -> float:
    if issued_count == 0:
        return 0.0
    return round(returned_count / issued_count, 4)


def _remaining(loan: Loan) -> int:
    return max(loan.cup_count - loan.returned_count, 0)


def _qr_value(loan: Loan) -> str:
    return generate_qr_value(loan.invoice_code, loan.issued_store.code)


def _is_expired(loan: Loan) -> bool:
    return loan.returned_count < loan.cup_count and now_taipei() > loan.due_at


def _is_abnormal(loan: Loan) -> bool:
    return bool(loan.return_condition and loan.return_condition != "normal")


def _invoice_summary(loan: Loan) -> GovernmentInvoiceSummary:
    return GovernmentInvoiceSummary(
        loanId=loan.id,
        invoiceCode=loan.invoice_code,
        qrValue=_qr_value(loan),
        storeId=loan.issued_store_id,
        storeCode=loan.issued_store.code,
        storeName=loan.issued_store.name,
        status=loan.status,
        containerType=loan.container_type,
        totalCupCount=loan.cup_count,
        returnedCount=loan.returned_count,
        remainingCupCount=_remaining(loan),
        issuedAt=loan.issued_at,
        dueAt=loan.due_at,
        returnedAt=loan.returned_at,
    )


def _bounded_loans(db: Session, from_at: datetime, to_at: datetime):
    return list(
        db.scalars(
            select(Loan)
            .where(Loan.issued_at >= from_at, Loan.issued_at <= to_at)
            .order_by(Loan.issued_at.desc(), Loan.id.desc())
        )
    )


def _government_login_response(user: GovernmentUser) -> GovernmentLoginResponse:
    token = create_access_token({"sub": user.user_email, "userId": user.id, "role": "government"})
    return GovernmentLoginResponse(
        accessToken=token,
        tokenType="bearer",
        user=GovernmentUserResponse(id=user.id, userEmail=user.user_email),
    )


@router.post("/auth/register", response_model=GovernmentLoginResponse, status_code=status.HTTP_201_CREATED)
def government_register(payload: GovernmentRegisterRequest, db: Session = Depends(get_db)) -> GovernmentLoginResponse:
    existing_user = db.scalar(select(GovernmentUser).where(GovernmentUser.user_email == payload.user_email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already exists")

    user = GovernmentUser(
        username=payload.user_email,
        user_email=payload.user_email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _government_login_response(user)


@router.post("/auth/login", response_model=GovernmentLoginResponse)
def government_login(payload: LoginRequest, db: Session = Depends(get_db)) -> GovernmentLoginResponse:
    user = db.scalar(select(GovernmentUser).where(GovernmentUser.user_email == payload.user_email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    return _government_login_response(user)


@router.get("/overview", response_model=GovernmentOverviewResponse)
def get_government_overview(
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentOverviewResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    loans = _bounded_loans(db, from_at, to_at)

    issued_count = sum(loan.cup_count for loan in loans)
    returned_count = sum(loan.returned_count for loan in loans)
    abnormal_count = sum(loan.returned_count for loan in loans if _is_abnormal(loan))
    overdue_count = sum(_remaining(loan) for loan in loans if _is_expired(loan))

    return GovernmentOverviewResponse(
        **{"from": from_at, "to": to_at},
        issuedCupCount=issued_count,
        returnedCupCount=returned_count,
        remainingCupCount=sum(_remaining(loan) for loan in loans),
        recoveryRate=_rate(returned_count, issued_count),
        activeInvoiceCount=sum(1 for loan in loans if loan.status == "active"),
        partialReturnedInvoiceCount=sum(1 for loan in loans if loan.status == "partial_returned"),
        returnedInvoiceCount=sum(1 for loan in loans if loan.status == "returned"),
        overdueCupCount=overdue_count,
        abnormalCupCount=abnormal_count,
    )


@router.get("/stores", response_model=GovernmentStoresResponse)
def get_government_stores(
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentStoresResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    stores = list(db.scalars(select(Store).order_by(Store.id)))
    loans = _bounded_loans(db, from_at, to_at)
    events = list(db.scalars(select(ScanEvent).where(ScanEvent.created_at >= from_at, ScanEvent.created_at <= to_at)))

    rows = []
    for store in stores:
        issued_loans = [loan for loan in loans if loan.issued_store_id == store.id]
        returned_loans = [loan for loan in loans if loan.returned_store_id == store.id]
        issued_count = sum(loan.cup_count for loan in issued_loans)
        returned_count = sum(loan.returned_count for loan in returned_loans)
        last_values = [loan.issued_at for loan in issued_loans]
        last_values.extend(event.created_at for event in events if event.store_id == store.id)

        rows.append(
            GovernmentStoreStatsResponse(
                storeId=store.id,
                storeCode=store.code,
                storeName=store.name,
                issuedCupCount=issued_count,
                returnedCupCount=returned_count,
                remainingCupCount=sum(_remaining(loan) for loan in issued_loans),
                crossStoreReturnedCount=sum(
                    loan.returned_count for loan in returned_loans if loan.issued_store_id != loan.returned_store_id
                ),
                abnormalCupCount=sum(loan.returned_count for loan in returned_loans if _is_abnormal(loan)),
                recoveryRate=_rate(returned_count, issued_count),
                lastActivityAt=max(last_values) if last_values else None,
            )
        )

    return GovernmentStoresResponse(**{"from": from_at, "to": to_at}, stores=rows)


@router.get("/invoices", response_model=GovernmentInvoicesResponse)
def get_government_invoices(
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    store_id: Optional[int] = Query(default=None, alias="storeId"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentInvoicesResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    statement = select(Loan).where(Loan.issued_at >= from_at, Loan.issued_at <= to_at)
    if store_id is not None:
        statement = statement.where(Loan.issued_store_id == store_id)
    if status_filter is not None:
        statement = statement.where(Loan.status == status_filter)
    statement = statement.order_by(Loan.issued_at.desc(), Loan.id.desc())
    loans = list(db.scalars(statement))

    return GovernmentInvoicesResponse(
        **{"from": from_at, "to": to_at},
        invoices=[_invoice_summary(loan) for loan in loans],
    )


@router.get("/invoices/{loan_id}", response_model=GovernmentInvoiceDetailResponse)
def get_government_invoice_detail(
    loan_id: int,
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentInvoiceDetailResponse:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice batch not found")

    summary = _invoice_summary(loan).model_dump(by_alias=True)
    scan_events = [
        GovernmentScanEventResponse(
            id=event.id,
            result=event.result,
            reason=event.reason,
            note=event.note,
            storeId=event.store_id,
            storeCode=event.store.code,
            storeName=event.store.name,
            createdAt=event.created_at,
        )
        for event in sorted(loan.scan_events, key=lambda event: event.created_at)
    ]

    return GovernmentInvoiceDetailResponse(
        **summary,
        returnedStoreId=loan.returned_store_id,
        returnedStoreCode=loan.returned_store.code if loan.returned_store else None,
        returnedStoreName=loan.returned_store.name if loan.returned_store else None,
        refundReason=loan.refund_ledger.reason if loan.refund_ledger else None,
        isExpired=_is_expired(loan),
        isAbnormal=_is_abnormal(loan),
        scanEvents=scan_events,
    )


@router.get("/anomalies", response_model=GovernmentAnomaliesResponse)
def get_government_anomalies(
    from_at: datetime = Query(..., alias="from"),
    to_at: datetime = Query(..., alias="to"),
    store_id: Optional[int] = Query(default=None, alias="storeId"),
    anomaly_type: Optional[str] = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentAnomaliesResponse:
    from_at = normalize_taipei(from_at)
    to_at = normalize_taipei(to_at)
    statement = select(ScanEvent).where(ScanEvent.created_at >= from_at, ScanEvent.created_at <= to_at)
    statement = statement.where(
        or_(
            ScanEvent.result != "returned",
            ScanEvent.reason.is_not(None),
        )
    )
    if store_id is not None:
        statement = statement.where(ScanEvent.store_id == store_id)
    if anomaly_type is not None:
        statement = statement.where(or_(ScanEvent.result == anomaly_type, ScanEvent.reason == anomaly_type))
    statement = statement.order_by(ScanEvent.created_at.desc(), ScanEvent.id.desc())
    events = list(db.scalars(statement))

    anomalies = []
    for event in events:
        loan = event.loan
        anomalies.append(
            GovernmentAnomalyResponse(
                eventId=event.id,
                eventType=event.event_type,
                result=event.result,
                reason=event.reason,
                note=event.note,
                storeId=event.store_id,
                storeCode=event.store.code,
                storeName=event.store.name,
                loanId=loan.id if loan else None,
                invoiceCode=loan.invoice_code if loan else None,
                qrValue=_qr_value(loan) if loan else None,
                totalCupCount=loan.cup_count if loan else None,
                returnedCount=loan.returned_count if loan else None,
                createdAt=event.created_at,
            )
        )

    return GovernmentAnomaliesResponse(**{"from": from_at, "to": to_at}, anomalies=anomalies)


@router.get("/daily/sold", response_model=GovernmentDailySoldStatsResponse)
def get_government_daily_sold_stats(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    store_id: Optional[int] = Query(default=None, alias="storeId"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentDailySoldStatsResponse:
    rows = read_daily_sold_summary(
        from_date,
        to_date,
        store_id=store_id,
        container_type=container_type.value if container_type is not None else None,
    )

    return GovernmentDailySoldStatsResponse(
        **{"from": from_date, "to": to_date},
        rows=[
            GovernmentDailySoldStatsRow(
                statDate=row["statDate"],
                storeId=row["storeId"],
                storeCode=row["storeCode"],
                storeName=row["storeName"],
                containerType=row["containerType"],
                soldCount=row["soldCount"],
            )
            for row in rows
        ],
    )


@router.get("/daily/recovered", response_model=GovernmentDailyRecoveredStatsResponse)
def get_government_daily_recovered_stats(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    store_id: Optional[int] = Query(default=None, alias="storeId"),
    container_type: Optional[ContainerType] = Query(default=None, alias="containerType"),
    db: Session = Depends(get_db),
    _: GovernmentUser = Depends(get_current_government_user),
) -> GovernmentDailyRecoveredStatsResponse:
    rows = read_daily_recovered_summary(
        from_date,
        to_date,
        store_id=store_id,
        container_type=container_type.value if container_type is not None else None,
    )

    return GovernmentDailyRecoveredStatsResponse(
        **{"from": from_date, "to": to_date},
        rows=[
            GovernmentDailyRecoveredStatsRow(
                statDate=row["statDate"],
                storeId=row["storeId"],
                storeCode=row["storeCode"],
                storeName=row["storeName"],
                containerType=row["containerType"],
                recoveredCount=row["recoveredCount"],
                normalCount=row["normalCount"],
                expiredCount=row["expiredCount"],
                abnormalCount=row["abnormalCount"],
                crossStoreCount=row["crossStoreCount"],
            )
            for row in rows
        ],
    )
