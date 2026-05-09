from datetime import date, datetime
from enum import Enum
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_user_email_alias(data):
    if not isinstance(data, dict):
        return data
    if "userEmail" in data or "user_email" in data:
        return data

    normalized = dict(data)
    for alias in ("useremail", "email", "username"):
        if alias in normalized:
            normalized["userEmail"] = normalized[alias]
            break
    return normalized


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CategoryLabel(str, Enum):
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

    @model_validator(mode="before")
    @classmethod
    def normalize_user_email_alias(cls, data):
        return _normalize_user_email_alias(data)

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
    region: str = Field(default="未設定", min_length=1, max_length=80)

    @model_validator(mode="before")
    @classmethod
    def normalize_user_email_alias(cls, data):
        return _normalize_user_email_alias(data)

    @field_validator("user_email")
    @classmethod
    def validate_user_email(cls, value: str) -> str:
        return LoginRequest.validate_user_email(value)

    @field_validator("region")
    @classmethod
    def normalize_region(cls, value: str) -> str:
        return value.strip() or "未設定"


class GovernmentRegisterRequest(APIModel):
    user_email: str = Field(alias="userEmail", min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def normalize_user_email_alias(cls, data):
        return _normalize_user_email_alias(data)

    @field_validator("user_email")
    @classmethod
    def validate_user_email(cls, value: str) -> str:
        return LoginRequest.validate_user_email(value)


class StoreResponse(APIModel):
    id: int
    code: str
    name: str
    region: str


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
    category: CategoryLabel = Field(alias="category")
    count: int = Field(alias="count", ge=1, le=100)


class QRCodeResponse(APIModel):
    loan_id: int = Field(alias="loanId")
    qr_value: str = Field(alias="qrValue")
    invoice_code: str = Field(alias="invoiceCode")
    store_code: str = Field(alias="storeCode")
    category: CategoryLabel = Field(alias="category")
    added_count: int = Field(alias="addedCount")
    total_count: int = Field(alias="totalCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_count: int = Field(alias="remainingCount")
    issued_at: datetime = Field(alias="issuedAt")
    due_at: datetime = Field(alias="dueAt")


class ReturnScanRequest(APIModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    qr_value: str = Field(alias="qrValue", min_length=1)


class ReturnScanResponse(APIModel):
    accepted: bool
    loan_id: int = Field(alias="loanId")
    status: str
    category: CategoryLabel = Field(alias="category")
    invoice_code: str = Field(alias="invoiceCode")
    issued_store_id: int = Field(alias="issuedStoreId")
    returned_store_id: int = Field(alias="returnedStoreId")
    count: int = Field(alias="count")
    total_count: int = Field(alias="totalCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_count: int = Field(alias="remainingCount")
    refund_reason: str = Field(alias="refundReason")
    is_expired: bool = Field(alias="isExpired")
    is_abnormal: bool = Field(alias="isAbnormal")
    due_at: datetime = Field(alias="dueAt")
    returned_at: datetime = Field(alias="returnedAt")


class CategoryCount(APIModel):
    category: CategoryLabel
    count: int


class MerchantSoldStatsRow(APIModel):
    stat_date: date = Field(alias="statDate")
    total_count: int = Field(alias="totalCount")
    category_counts: list[CategoryCount] = Field(alias="categoryCounts")


class MerchantSoldStatsResponse(APIModel):
    store_id: int = Field(alias="storeId")
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    rows: list[MerchantSoldStatsRow]


class MerchantRecoveredStatsRow(APIModel):
    stat_date: date = Field(alias="statDate")
    total_count: int = Field(alias="totalCount")
    category_counts: list[CategoryCount] = Field(alias="categoryCounts")
    normal_count: int = Field(alias="normalCount")
    expired_count: int = Field(alias="expiredCount")
    abnormal_count: int = Field(alias="abnormalCount")
    cross_store_count: int = Field(alias="crossStoreCount")


class MerchantRecoveredStatsResponse(APIModel):
    store_id: int = Field(alias="storeId")
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    rows: list[MerchantRecoveredStatsRow]


class GovernmentWebDailyUsageRow(APIModel):
    stat_date: date = Field(alias="statDate")
    issued_count: int = Field(alias="issuedCount")
    returned_count: int = Field(alias="returnedCount")


class GovernmentWebMonthlyUsageResponse(APIModel):
    month: str
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    issued_count: int = Field(alias="issuedCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_count: int = Field(alias="remainingCount")
    recovery_rate: float = Field(alias="recoveryRate")
    active_invoice_count: int = Field(alias="activeInvoiceCount")
    partial_returned_invoice_count: int = Field(alias="partialReturnedInvoiceCount")
    returned_invoice_count: int = Field(alias="returnedInvoiceCount")
    overdue_count: int = Field(alias="overdueCount")
    abnormal_count: int = Field(alias="abnormalCount")
    daily: list[GovernmentWebDailyUsageRow]


class GovernmentWebEnterpriseCountsResponse(APIModel):
    month: str
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    month_joined_count: int = Field(alias="monthJoinedCount")
    total_enterprise_count: int = Field(alias="totalEnterpriseCount")


class GovernmentWebRegionDistributionRow(APIModel):
    region: str
    enterprise_count: int = Field(alias="enterpriseCount")


class GovernmentWebRegionDistributionResponse(APIModel):
    total_enterprise_count: int = Field(alias="totalEnterpriseCount")
    regions: list[GovernmentWebRegionDistributionRow]


class GovernmentWebCupUsageRankingRow(APIModel):
    rank: int
    store_id: int = Field(alias="storeId")
    store_code: str = Field(alias="storeCode")
    store_name: str = Field(alias="storeName")
    region: str
    issued_count: int = Field(alias="issuedCount")
    returned_count: int = Field(alias="returnedCount")
    remaining_count: int = Field(alias="remainingCount")
    recovery_rate: float = Field(alias="recoveryRate")


class GovernmentWebCupUsageRankingResponse(APIModel):
    month: str
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    category: CategoryLabel
    rankings: list[GovernmentWebCupUsageRankingRow]


class GovernmentWebStoreProfile(APIModel):
    id: int
    code: str
    name: str
    region: str
    created_at: datetime = Field(alias="createdAt")


class GovernmentWebStoreStatusResponse(APIModel):
    month: str
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")
    store: GovernmentWebStoreProfile
    issued_count: int = Field(alias="issuedCount")
    returned_count: int = Field(alias="returnedCount")
    recovered_count: int = Field(alias="recoveredCount")
    remaining_count: int = Field(alias="remainingCount")
    recovery_rate: float = Field(alias="recoveryRate")
    cup_issued_count: int = Field(alias="cupIssuedCount")
    cup_returned_count: int = Field(alias="cupReturnedCount")
    meal_box_issued_count: int = Field(alias="mealBoxIssuedCount")
    meal_box_returned_count: int = Field(alias="mealBoxReturnedCount")
    overdue_count: int = Field(alias="overdueCount")
    abnormal_count: int = Field(alias="abnormalCount")
    cross_store_recovered_count: int = Field(alias="crossStoreRecoveredCount")
    last_activity_at: Optional[datetime] = Field(default=None, alias="lastActivityAt")
