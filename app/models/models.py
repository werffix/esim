import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def gen_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    referral_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    referred_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    total_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    # Relationships
    referred_by: Mapped[Optional["User"]] = relationship("User", remote_side="User.id", foreign_keys=[referred_by_id])
    referrals: Mapped[list["User"]] = relationship("User", foreign_keys=[referred_by_id], back_populates="referred_by")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")
    esims: Mapped[list["Esim"]] = relationship("Esim", back_populates="user")
    referral_earnings: Mapped[list["ReferralEarning"]] = relationship("ReferralEarning", foreign_keys="ReferralEarning.referrer_id", back_populates="referrer")

    __table_args__ = (
        Index("ix_users_referral_code", "referral_code"),
    )

    def __repr__(self) -> str:
        return f"<User {self.telegram_id} ({self.first_name})>"


class ReferralEarning(TimestampMixin, Base):
    __tablename__ = "referral_earnings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    referrer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    referred_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    referrer: Mapped["User"] = relationship("User", foreign_keys=[referrer_id], back_populates="referral_earnings")
    order: Mapped["Order"] = relationship("Order")

    __table_args__ = (
        Index("ix_referral_earnings_referrer", "referrer_id"),
    )


class Country(TimestampMixin, Base):
    __tablename__ = "countries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    flag_emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    plans: Mapped[list["Plan"]] = relationship("Plan", back_populates="country")

    def __repr__(self) -> str:
        return f"<Country {self.code} {self.name}>"


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    nova_plan_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    country_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_gb: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    markup_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=20.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    country: Mapped["Country"] = relationship("Country", back_populates="plans")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="plan")

    @property
    def final_price(self) -> Decimal:
        return round(self.base_price * Decimal(str(1 + self.markup_percent / 100)), 2)

    def __repr__(self) -> str:
        return f"<Plan {self.nova_plan_id} {self.data_gb}GB {self.duration_days}d>"


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    external_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    # pending -> paid -> esim_created -> completed | failed | refunded
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    payment_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="orders")
    plan: Mapped["Plan"] = relationship("Plan", back_populates="orders")
    esim: Mapped[Optional["Esim"]] = relationship("Esim", back_populates="order", uselist=False)
    payment: Mapped[Optional["Payment"]] = relationship("Payment", back_populates="order", uselist=False)

    __table_args__ = (
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Order {self.external_ref} {self.status}>"


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False)
    platega_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    # pending -> success | failed | expired
    payment_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="payment")

    __table_args__ = (
        Index("ix_payments_status", "status"),
    )


class Esim(TimestampMixin, Base):
    __tablename__ = "esims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    iccid: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    lpa: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activation_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qr_code_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qr_code_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # base64
    status: Mapped[str] = mapped_column(String(50), default="inactive", nullable=False)
    # inactive -> active -> expired | cancelled | deleted
    data_total_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    data_used_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    nova_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="esim")
    user: Mapped["User"] = relationship("User", back_populates="esims")

    __table_args__ = (
        Index("ix_esims_user_id", "user_id"),
        Index("ix_esims_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Esim {self.iccid} {self.status}>"


class AdminLog(TimestampMixin, Base):
    __tablename__ = "admin_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_admin_logs_admin", "admin_telegram_id"),
        Index("ix_admin_logs_created_at", "created_at"),
    )
