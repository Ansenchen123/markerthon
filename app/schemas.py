from datetime import datetime
from enum import Enum
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ContainerType(str, Enum):
    cup = "cup"
    meal_box = "meal_box"


class ReturnCondition(str, Enum):
    normal = "normal"
    damaged = "damaged"
    polluted = "polluted"
    other = "other"


class LoginRequest(APIModel):
    user_email: str = Field(alias="userEmail", min_length=3, max_length=255)
    password: str

    @field_validator("user_email")
    @classmethod
    def validate_user_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Invalid email format")
        return normalized


class MerchantRegisterRequest(APIModel):
    user_email: str = Field(alias="userEmail", min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    store_name: str = Field(alias="storeName", min_length=1, max_length=120)

    @field_validator("user_email")
    @classmethod
    def validate_user_email(cls, value: str) -> str:
        return LoginRequest.validate_user_email(value)


class GovernmentRegisterRequest(APIModel):
    user_email: str = Field(alias="userEmail", min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("user_email")
    @classmethod
    def validate_user_email(cls, value: str) -> str:
        return LoginRequest.validate_user_email(value)


class StoreResponse(APIModel):
    id: int
    code: str
    name: str


class LoginResponse(APIModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    store: StoreResponse


class GovernmentUserResponse(APIModel):
    id: int
    user_email: str = Field(alias="userEmail")


class GovernmentLoginResponse(APIModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    user: GovernmentUserResponse


class QRCodeCreate(APIModel):
    invoice_code: str = Field(alias="invoiceCode", min_length=1, max_length=80)
    cup_count: int = Field(alias="cupCount", ge=1, le=100)


class QRCodeResponse(APIModel):
    loan_id: int = Field(alias="loanId")
    qr_value: str = Field(alias="qrValue")
    invoice_code: str = Field(alias="invoiceCode")
    store_code: str = Field(alias="storeCode")
    added_cup_count: int = Field(alias="addedCupCount")
    total_cup_count: int = Field(alias="totalCupCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_cup_count: int = Field(alias="remainingCupCount")
    issued_at: datetime = Field(alias="issuedAt")
    due_at: datetime = Field(alias="dueAt")


class ReturnScanRequest(APIModel):
    qr_value: str = Field(alias="qrValue", min_length=1)
    condition: ReturnCondition = ReturnCondition.normal
    note: Optional[str] = None


class ReturnScanResponse(APIModel):
    accepted: bool
    loan_id: int = Field(alias="loanId")
    status: str
    container_type: ContainerType = Field(alias="containerType")
    invoice_code: str = Field(alias="invoiceCode")
    issued_store_id: int = Field(alias="issuedStoreId")
    returned_store_id: int = Field(alias="returnedStoreId")
    cup_count: int = Field(alias="cupCount")
    total_cup_count: int = Field(alias="totalCupCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_cup_count: int = Field(alias="remainingCupCount")
    refund_reason: str = Field(alias="refundReason")
    is_expired: bool = Field(alias="isExpired")
    is_abnormal: bool = Field(alias="isAbnormal")
    due_at: datetime = Field(alias="dueAt")
    returned_at: datetime = Field(alias="returnedAt")


class MerchantSoldStatsResponse(APIModel):
    store_id: int = Field(alias="storeId")
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    container_type: Optional[ContainerType] = Field(default=None, alias="containerType")
    total_count: int = Field(alias="totalCount")
    cup_count: int = Field(alias="cupCount")
    meal_box_count: int = Field(alias="mealBoxCount")


class MerchantRecoveredStatsResponse(APIModel):
    store_id: int = Field(alias="storeId")
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    container_type: Optional[ContainerType] = Field(default=None, alias="containerType")
    total_count: int = Field(alias="totalCount")
    normal_count: int = Field(alias="normalCount")
    expired_count: int = Field(alias="expiredCount")
    abnormal_count: int = Field(alias="abnormalCount")
    cross_store_count: int = Field(alias="crossStoreCount")


class GovernmentOverviewResponse(APIModel):
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    issued_cup_count: int = Field(alias="issuedCupCount")
    returned_cup_count: int = Field(alias="returnedCupCount")
    remaining_cup_count: int = Field(alias="remainingCupCount")
    recovery_rate: float = Field(alias="recoveryRate")
    active_invoice_count: int = Field(alias="activeInvoiceCount")
    returned_invoice_count: int = Field(alias="returnedInvoiceCount")
    partial_returned_invoice_count: int = Field(alias="partialReturnedInvoiceCount")
    overdue_cup_count: int = Field(alias="overdueCupCount")
    abnormal_cup_count: int = Field(alias="abnormalCupCount")


class GovernmentStoreStatsResponse(APIModel):
    store_id: int = Field(alias="storeId")
    store_code: str = Field(alias="storeCode")
    store_name: str = Field(alias="storeName")
    issued_cup_count: int = Field(alias="issuedCupCount")
    returned_cup_count: int = Field(alias="returnedCupCount")
    remaining_cup_count: int = Field(alias="remainingCupCount")
    cross_store_returned_count: int = Field(alias="crossStoreReturnedCount")
    abnormal_cup_count: int = Field(alias="abnormalCupCount")
    recovery_rate: float = Field(alias="recoveryRate")
    last_activity_at: Optional[datetime] = Field(default=None, alias="lastActivityAt")


class GovernmentStoresResponse(APIModel):
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    stores: list[GovernmentStoreStatsResponse]


class GovernmentInvoiceSummary(APIModel):
    loan_id: int = Field(alias="loanId")
    invoice_code: str = Field(alias="invoiceCode")
    qr_value: str = Field(alias="qrValue")
    store_id: int = Field(alias="storeId")
    store_code: str = Field(alias="storeCode")
    store_name: str = Field(alias="storeName")
    status: str
    container_type: ContainerType = Field(alias="containerType")
    total_cup_count: int = Field(alias="totalCupCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_cup_count: int = Field(alias="remainingCupCount")
    issued_at: datetime = Field(alias="issuedAt")
    due_at: datetime = Field(alias="dueAt")
    returned_at: Optional[datetime] = Field(default=None, alias="returnedAt")


class GovernmentInvoicesResponse(APIModel):
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    invoices: list[GovernmentInvoiceSummary]


class GovernmentScanEventResponse(APIModel):
    id: int
    result: str
    reason: Optional[str] = None
    note: Optional[str] = None
    store_id: int = Field(alias="storeId")
    store_code: str = Field(alias="storeCode")
    store_name: str = Field(alias="storeName")
    created_at: datetime = Field(alias="createdAt")


class GovernmentInvoiceDetailResponse(GovernmentInvoiceSummary):
    returned_store_id: Optional[int] = Field(default=None, alias="returnedStoreId")
    returned_store_code: Optional[str] = Field(default=None, alias="returnedStoreCode")
    returned_store_name: Optional[str] = Field(default=None, alias="returnedStoreName")
    refund_reason: Optional[str] = Field(default=None, alias="refundReason")
    is_expired: bool = Field(alias="isExpired")
    is_abnormal: bool = Field(alias="isAbnormal")
    scan_events: list[GovernmentScanEventResponse] = Field(alias="scanEvents")


class GovernmentAnomalyResponse(APIModel):
    event_id: int = Field(alias="eventId")
    event_type: str = Field(alias="eventType")
    result: str
    reason: Optional[str] = None
    note: Optional[str] = None
    store_id: int = Field(alias="storeId")
    store_code: str = Field(alias="storeCode")
    store_name: str = Field(alias="storeName")
    loan_id: Optional[int] = Field(default=None, alias="loanId")
    invoice_code: Optional[str] = Field(default=None, alias="invoiceCode")
    qr_value: Optional[str] = Field(default=None, alias="qrValue")
    total_cup_count: Optional[int] = Field(default=None, alias="totalCupCount")
    returned_count: Optional[int] = Field(default=None, alias="returnedCount")
    created_at: datetime = Field(alias="createdAt")


class GovernmentAnomaliesResponse(APIModel):
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    anomalies: list[GovernmentAnomalyResponse]
