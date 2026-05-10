import uuid
from decimal import Decimal
from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import Base
from app.models.models import (
    AdminLog,
    Country,
    Esim,
    Order,
    Payment,
    Plan,
    ReferralEarning,
    User,
)

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id: uuid.UUID) -> Optional[ModelT]:
        return await self.session.get(self.model, id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> ModelT:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return result.scalar_one()


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        first_name: str,
        username: Optional[str],
        last_name: Optional[str],
        language_code: str,
        referral_code: str,
        referred_by_id: Optional[uuid.UUID] = None,
    ) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            return user, False
        user = await self.create(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            last_name=last_name,
            language_code=language_code,
            referral_code=referral_code,
            referred_by_id=referred_by_id,
        )
        return user, True

    async def add_balance(self, user_id: uuid.UUID, amount: Decimal) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(balance=User.balance + amount)
        )

    async def add_total_spent(self, user_id: uuid.UUID, amount: Decimal) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(total_spent=User.total_spent + amount)
        )

    async def get_referrals(self, user_id: uuid.UUID) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.referred_by_id == user_id)
        )
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        total = await self.count()
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.is_active == True)
        )
        active = result.scalar_one()
        result2 = await self.session.execute(select(func.sum(User.total_spent)))
        total_spent = result2.scalar_one() or Decimal("0")
        return {"total": total, "active": active, "total_spent": total_spent}

    async def search(self, query: str, limit: int = 20) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(
                (User.username.ilike(f"%{query}%"))
                | (User.first_name.ilike(f"%{query}%"))
            )
            .limit(limit)
        )
        return list(result.scalars().all())


class CountryRepository(BaseRepository[Country]):
    model = Country

    async def get_by_code(self, code: str) -> Optional[Country]:
        result = await self.session.execute(
            select(Country).where(Country.code == code)
        )
        return result.scalar_one_or_none()

    async def get_active(self) -> list[Country]:
        result = await self.session.execute(
            select(Country)
            .where(Country.is_active == True)
            .order_by(Country.sort_order, Country.name)
        )
        return list(result.scalars().all())

    async def upsert(self, code: str, name: str, flag_emoji: Optional[str] = None) -> Country:
        existing = await self.get_by_code(code)
        if existing:
            existing.name = name
            if flag_emoji:
                existing.flag_emoji = flag_emoji
            await self.session.flush()
            return existing
        return await self.create(code=code, name=name, flag_emoji=flag_emoji)


class PlanRepository(BaseRepository[Plan]):
    model = Plan

    async def get_by_nova_id(self, nova_plan_id: str) -> Optional[Plan]:
        result = await self.session.execute(
            select(Plan).where(Plan.nova_plan_id == nova_plan_id)
        )
        return result.scalar_one_or_none()

    async def get_by_country(self, country_id: uuid.UUID) -> list[Plan]:
        result = await self.session.execute(
            select(Plan)
            .where(Plan.country_id == country_id, Plan.is_active == True)
            .order_by(Plan.data_gb, Plan.duration_days)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        nova_plan_id: str,
        country_id: uuid.UUID,
        name: str,
        data_gb: float,
        duration_days: int,
        base_price: Decimal,
        markup_percent: float,
        extra_data: Optional[dict] = None,
    ) -> Plan:
        existing = await self.get_by_nova_id(nova_plan_id)
        if existing:
            existing.name = name
            existing.data_gb = data_gb
            existing.duration_days = duration_days
            existing.base_price = base_price
            existing.markup_percent = markup_percent
            existing.extra_data = extra_data
            await self.session.flush()
            return existing
        return await self.create(
            nova_plan_id=nova_plan_id,
            country_id=country_id,
            name=name,
            data_gb=data_gb,
            duration_days=duration_days,
            base_price=base_price,
            markup_percent=markup_percent,
            extra_data=extra_data,
        )


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def get_by_external_ref(self, external_ref: str) -> Optional[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.external_ref == external_ref)
            .options(selectinload(Order.user), selectinload(Order.plan))
        )
        return result.scalar_one_or_none()

    async def get_by_payment_id(self, payment_id: str) -> Optional[Order]:
        result = await self.session.execute(
            select(Order).where(Order.payment_id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_user_orders(self, user_id: uuid.UUID, limit: int = 20) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .options(selectinload(Order.plan), selectinload(Order.esim))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(self, order_id: uuid.UUID, status: str, **extra) -> None:
        values = {"status": status, **extra}
        await self.session.execute(
            update(Order).where(Order.id == order_id).values(**values)
        )

    async def get_revenue_stats(self) -> dict:
        from sqlalchemy import and_
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_r = await self.session.execute(
            select(func.sum(Order.amount)).where(Order.status == "completed")
        )
        today_r = await self.session.execute(
            select(func.sum(Order.amount)).where(
                Order.status == "completed",
                Order.created_at >= today_start,
            )
        )
        month_r = await self.session.execute(
            select(func.sum(Order.amount)).where(
                Order.status == "completed",
                Order.created_at >= month_start,
            )
        )
        count_r = await self.session.execute(
            select(func.count()).select_from(Order).where(Order.status == "completed")
        )
        return {
            "total": total_r.scalar_one() or Decimal("0"),
            "today": today_r.scalar_one() or Decimal("0"),
            "month": month_r.scalar_one() or Decimal("0"),
            "count": count_r.scalar_one(),
        }


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def get_by_platega_id(self, platega_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.platega_payment_id == platega_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, payment_id: uuid.UUID, status: str, **extra) -> None:
        values = {"status": status, **extra}
        await self.session.execute(
            update(Payment).where(Payment.id == payment_id).values(**values)
        )


class EsimRepository(BaseRepository[Esim]):
    model = Esim

    async def get_by_iccid(self, iccid: str) -> Optional[Esim]:
        result = await self.session.execute(
            select(Esim).where(Esim.iccid == iccid)
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> Optional[Esim]:
        result = await self.session.execute(
            select(Esim).where(Esim.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_user_esims(self, user_id: uuid.UUID) -> list[Esim]:
        result = await self.session.execute(
            select(Esim)
            .where(Esim.user_id == user_id)
            .options(selectinload(Esim.order).selectinload(Order.plan))
            .order_by(Esim.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_active_for_status_update(self, limit: int = 50) -> list[Esim]:
        """Get active eSIMs that need status refresh."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        result = await self.session.execute(
            select(Esim)
            .where(
                Esim.status.in_(["inactive", "active"]),
                (Esim.last_status_check == None) | (Esim.last_status_check < cutoff),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(self, esim_id: uuid.UUID, **kwargs) -> None:
        from datetime import datetime
        kwargs["last_status_check"] = datetime.utcnow()
        await self.session.execute(
            update(Esim).where(Esim.id == esim_id).values(**kwargs)
        )


class AdminLogRepository(BaseRepository[AdminLog]):
    model = AdminLog

    async def log(
        self,
        admin_telegram_id: int,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AdminLog:
        return await self.create(
            admin_telegram_id=admin_telegram_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )

    async def get_recent(self, limit: int = 50) -> list[AdminLog]:
        result = await self.session.execute(
            select(AdminLog).order_by(AdminLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


class ReferralEarningRepository(BaseRepository[ReferralEarning]):
    model = ReferralEarning

    async def get_user_earnings(self, referrer_id: uuid.UUID) -> list[ReferralEarning]:
        result = await self.session.execute(
            select(ReferralEarning)
            .where(ReferralEarning.referrer_id == referrer_id)
            .order_by(ReferralEarning.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_total_earned(self, referrer_id: uuid.UUID) -> Decimal:
        result = await self.session.execute(
            select(func.sum(ReferralEarning.amount))
            .where(ReferralEarning.referrer_id == referrer_id)
        )
        return result.scalar_one() or Decimal("0")
