from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    username: str
    password: str


class StoreResponse(APIModel):
    id: int
    code: str
    name: str


class LoginResponse(APIModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    store: StoreResponse


class QRCodeCreate(APIModel):
    container_type: ContainerType = Field(alias="containerType")
    invoice_code: str = Field(alias="invoiceCode", min_length=1, max_length=80)
    note: Optional[str] = None


class QRCodeResponse(APIModel):
    loan_id: int = Field(alias="loanId")
    qr_value: str = Field(alias="qrValue")
    container_type: ContainerType = Field(alias="containerType")
    invoice_code: str = Field(alias="invoiceCode")
    invoice_sequence: int = Field(alias="invoiceSequence")
    deposit_amount: int = Field(alias="depositAmount")
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
    invoice_sequence: int = Field(alias="invoiceSequence")
    issued_store_id: int = Field(alias="issuedStoreId")
    returned_store_id: int = Field(alias="returnedStoreId")
    deposit_amount: int = Field(alias="depositAmount")
    refund_amount: int = Field(alias="refundAmount")
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
    deposit_total: int = Field(alias="depositTotal")


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
    refund_total: int = Field(alias="refundTotal")
