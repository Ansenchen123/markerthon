from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.time_utils import now_taipei


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True)
    code = Column(String(40), nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    region = Column(String(80), nullable=False, default="未設定", index=True)
    created_at = Column(DateTime, nullable=False, default=now_taipei)

    users = relationship("MerchantUser", back_populates="store")
    issued_loans = relationship("Loan", foreign_keys="Loan.issued_store_id", back_populates="issued_store")
    returned_loans = relationship("Loan", foreign_keys="Loan.returned_store_id", back_populates="returned_store")


class MerchantUser(Base):
    __tablename__ = "merchant_users"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    username = Column(String(80), nullable=False, unique=True, index=True)
    user_email = Column(String(255), nullable=True, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=now_taipei)

    store = relationship("Store", back_populates="users")


class GovernmentUser(Base):
    __tablename__ = "government_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, unique=True, index=True)
    user_email = Column(String(255), nullable=True, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=now_taipei)


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        UniqueConstraint("qr_token_hash", name="uq_loans_qr_token_hash"),
        UniqueConstraint(
            "issued_store_id",
            "invoice_code",
            "container_type",
            "invoice_sequence",
            name="uq_loans_invoice_store_type_sequence",
        ),
    )

    id = Column(Integer, primary_key=True)
    qr_token_hash = Column(String(64), nullable=False, index=True)
    issued_store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    invoice_code = Column(String(80), nullable=False, index=True)
    invoice_sequence = Column(Integer, nullable=False, default=1)
    item_count = Column(Integer, nullable=False, default=1)
    returned_count = Column(Integer, nullable=False, default=0)
    container_type = Column(String(20), nullable=False, index=True)
    deposit_amount = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)
    note = Column(Text, nullable=True)
    issued_at = Column(DateTime, nullable=False, default=now_taipei, index=True)
    due_at = Column(DateTime, nullable=False, index=True)
    returned_at = Column(DateTime, nullable=True, index=True)
    returned_store_id = Column(Integer, ForeignKey("stores.id"), nullable=True, index=True)
    return_condition = Column(String(20), nullable=True)
    abnormal_note = Column(Text, nullable=True)

    issued_store = relationship("Store", foreign_keys=[issued_store_id], back_populates="issued_loans")
    returned_store = relationship("Store", foreign_keys=[returned_store_id], back_populates="returned_loans")
    refund_ledger = relationship("RefundLedger", back_populates="loan", uselist=False)
    scan_events = relationship("ScanEvent", back_populates="loan")


class RefundLedger(Base):
    __tablename__ = "refund_ledgers"

    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, unique=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    refund_amount = Column(Integer, nullable=False)
    reason = Column(String(120), nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_taipei, index=True)

    loan = relationship("Loan", back_populates="refund_ledger")
    store = relationship("Store")


class ScanEvent(Base):
    __tablename__ = "scan_events"

    id = Column(Integer, primary_key=True)
    qr_token_hash = Column(String(64), nullable=False, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    event_type = Column(String(40), nullable=False, default="return_scan")
    result = Column(String(40), nullable=False, index=True)
    reason = Column(String(120), nullable=True, index=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_taipei, index=True)

    loan = relationship("Loan", back_populates="scan_events")
    store = relationship("Store")
