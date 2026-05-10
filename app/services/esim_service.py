import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheManager
from app.core.config import settings
from app.core.logging import get_logger
from app.esim.nova_client import NovaEsimClient, NovaEsimAPIError
from app.models.models import Country, Esim, Order, Plan
from app.repositories.repositories import (
    CountryRepository,
    EsimRepository,
    OrderRepository,
    PaymentRepository,
    PlanRepository,
    UserRepository,
    ReferralEarningRepository,
)

logger = get_logger(__name__)


class CatalogService:
    def __init__(self, session: AsyncSession, nova: NovaEsimClient, cache: CacheManager):
        self.session = session
        self.nova = nova
        self.cache = cache
        self.country_repo = CountryRepository(session)
        self.plan_repo = PlanRepository(session)

    async def sync_catalog(self) -> tuple[int, int]:
        """Sync countries and plans from Nova API. Returns (countries_count, plans_count)."""
        logger.info("catalog_sync_start")

        countries = await self.nova.get_countries()
        country_map: dict[str, Country] = {}
        for c in countries:
            flag = self._code_to_flag(c.country_code)
            country_obj = await self.country_repo.upsert(
                code=c.country_code, name=c.country_code, flag_emoji=flag
            )
            country_map[c.country_code] = country_obj
        await self.session.commit()

        plans = await self.nova.get_plans()
        plan_count = 0
        default_markup = settings.DEFAULT_MARKUP_PERCENT
        for p in plans:
            country_obj = country_map.get(p.country_code)
            if not country_obj:
                continue
            await self.plan_repo.upsert(
                nova_plan_id=p.id,
                country_id=country_obj.id,
                name=p.name,
                data_gb=p.data_gb or 0,
                duration_days=p.validity_days,
                base_price=Decimal(p.price_usd),
                markup_percent=default_markup,
                extra_data=None,
            )
            plan_count += 1
        await self.session.commit()

        # Invalidate caches
        await self.cache.delete_pattern("countries:*")
        await self.cache.delete_pattern("plans:*")

        logger.info("catalog_sync_done", countries=len(countries), plans=plan_count)
        return len(countries), plan_count

    async def get_active_countries(self) -> list[Country]:
        cache_key = "countries:active"
        cached = await self.cache.get(cache_key)
        if cached:
            # Deserialize from cache (return DB objects freshly)
            pass  # fallthrough to DB for simplicity — cache is advisory

        countries = await self.country_repo.get_active()
        return countries

    async def get_plans_for_country(self, country_id: uuid.UUID) -> list[Plan]:
        return await self.plan_repo.get_by_country(country_id)

    @staticmethod
    def _code_to_flag(code: str) -> str:
        """Convert ISO 3166-1 alpha-2 to flag emoji."""
        if len(code) != 2:
            return "🌐"
        offset = 127397
        return "".join(chr(ord(c) + offset) for c in code.upper())


class OrderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_repo = OrderRepository(session)
        self.user_repo = UserRepository(session)
        self.plan_repo = PlanRepository(session)

    async def create_order(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> Order:
        plan = await self.plan_repo.get(plan_id)
        if not plan or not plan.is_active:
            raise ValueError("Plan not found or inactive")

        external_ref = f"q1-{uuid.uuid4().hex[:16]}"
        amount = plan.final_price

        order = await self.order_repo.create(
            user_id=user_id,
            plan_id=plan.id,
            external_ref=external_ref,
            amount=amount,
            status="pending",
        )
        await self.session.commit()
        logger.info("order_created", order_id=str(order.id), external_ref=external_ref, amount=str(amount))
        return order

    async def mark_paid(self, external_ref: str, payment_id: str, paid_at: datetime) -> Optional[Order]:
        order = await self.order_repo.get_by_external_ref(external_ref)
        if not order:
            logger.error("order_not_found", external_ref=external_ref)
            return None
        if order.status not in ("pending",):
            logger.warning("order_already_processed", external_ref=external_ref, status=order.status)
            return order  # idempotent

        await self.order_repo.update_status(
            order.id, "paid", payment_id=payment_id, paid_at=paid_at
        )
        await self.session.commit()
        return order


class EsimService:
    def __init__(self, session: AsyncSession, nova: NovaEsimClient):
        self.session = session
        self.nova = nova
        self.esim_repo = EsimRepository(session)
        self.order_repo = OrderRepository(session)
        self.user_repo = UserRepository(session)
        self.referral_repo = ReferralEarningRepository(session)

    async def provision_esim(self, order: Order) -> Esim:
        """Purchase eSIM from Nova and store. Idempotent via external_ref."""
        # Check if already created
        existing = await self.esim_repo.get_by_order_id(order.id)
        if existing:
            logger.info("esim_already_provisioned", order_id=str(order.id), iccid=existing.iccid)
            return existing

        plan = await self.order_repo.session.get(Plan, order.plan_id)
        if not plan:
            raise ValueError("Plan not found for order")

        try:
            nova_esim = await self.nova.create_esim(
                plan_id=plan.nova_plan_id,
                external_ref=order.external_ref,
            )
        except NovaEsimAPIError as e:
            logger.error("nova_esim_creation_failed", order_id=str(order.id), error=str(e))
            await self.order_repo.update_status(order.id, "failed", error_message=str(e))
            await self.session.commit()
            raise

        # Fetch QR code
        qr_data = None
        try:
            qr = await self.nova.get_esim_qr(nova_esim.iccid)
            qr_data = qr.qr_base64
        except Exception as e:
            logger.warning("qr_fetch_failed", iccid=nova_esim.iccid, error=str(e))

        esim = await self.esim_repo.create(
            order_id=order.id,
            user_id=order.user_id,
            iccid=nova_esim.iccid,
            lpa=nova_esim.lpa,
            activation_code=nova_esim.activation_code,
            qr_code_url=nova_esim.qr_url,
            qr_code_data=qr_data,
            status="inactive",
            nova_data={
                "iccid": nova_esim.iccid,
                "lpa": nova_esim.lpa,
                "activation_code": nova_esim.activation_code,
            },
        )

        await self.order_repo.update_status(order.id, "esim_created")
        await self.user_repo.add_total_spent(order.user_id, order.amount)

        # Process referral bonus
        user = await self.user_repo.get(order.user_id)
        if user and user.referred_by_id:
            await self._process_referral(user, order)

        await self.session.commit()
        logger.info("esim_provisioned", iccid=nova_esim.iccid, order_id=str(order.id))
        return esim

    async def _process_referral(self, user, order: Order) -> None:
        percent = settings.REFERRAL_PERCENT
        bonus = round(order.amount * Decimal(str(percent / 100)), 2)
        if bonus <= 0:
            return
        await self.user_repo.add_balance(user.referred_by_id, bonus)
        await self.referral_repo.create(
            referrer_id=user.referred_by_id,
            referred_user_id=user.id,
            order_id=order.id,
            amount=bonus,
            percent=percent,
        )
        logger.info("referral_bonus_credited", referrer=str(user.referred_by_id), amount=str(bonus))

    async def refresh_esim_status(self, esim: Esim) -> Esim:
        try:
            detail = await self.nova.get_esim(esim.iccid)
            update_data = {
                "status": detail.status,
                "data_total_mb": detail.data_total_mb,
                "data_used_mb": detail.data_used_mb,
            }
            if detail.expires_at:
                from dateutil.parser import parse
                update_data["expires_at"] = parse(detail.expires_at)
            if detail.activated_at:
                from dateutil.parser import parse
                update_data["activated_at"] = parse(detail.activated_at)

            await self.esim_repo.update_status(esim.id, **update_data)
            await self.session.commit()
            for k, v in update_data.items():
                setattr(esim, k, v)
        except Exception as e:
            logger.warning("esim_status_refresh_failed", iccid=esim.iccid, error=str(e))
        return esim

    async def get_user_esims(self, user_id: uuid.UUID) -> list[Esim]:
        return await self.esim_repo.get_user_esims(user_id)
