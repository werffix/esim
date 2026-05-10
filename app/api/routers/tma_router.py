import hashlib
import hmac
import json
import urllib.parse
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import settings
from app.esim.nova_client import get_nova_client
from app.models.models import User
from app.repositories.repositories import CountryRepository, EsimRepository, OrderRepository, PlanRepository
from app.services.esim_service import CatalogService, EsimService, OrderService
from app.db.database import get_session

router = APIRouter(tags=["tma"])


def _verify_init_data(init_data: str) -> dict[str, Any] | None:
    parsed = urllib.parse.parse_qs(init_data, keep_blank_values=True)
    data = {k: v[0] for k, v in parsed.items()}

    received_hash = data.pop("hash", None)
    if not received_hash:
        return None

    items = sorted(data.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if computed_hash != received_hash:
        return None

    if "user" in data:
        data["user"] = json.loads(data["user"])

    return data


@router.get("/tma")
async def serve_tma():
    with open("app/static/tma.html") as f:
        return HTMLResponse(f.read())


@router.post("/tma/init")
async def tma_init(body: dict, request: Request):
    init_data = body.get("initData", "")
    verified = _verify_init_data(init_data)
    if not verified:
        raise HTTPException(401, "Invalid init data")

    tg_user = verified.get("user", {})
    telegram_id = tg_user.get("id")

    async with get_session() as session:
        from app.repositories.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=tg_user.get("username"),
                first_name=tg_user.get("first_name", ""),
                last_name=tg_user.get("last_name", ""),
                language_code=tg_user.get("language_code", "en"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        nova = await get_nova_client()
        cache = await get_cache()
        catalog = CatalogService(session, nova, cache)
        all_countries = await catalog.get_active_countries()
        esim_repo = EsimRepository(session)
        esims = await esim_repo.get_user_esims(user.id)

        esim_list = []
        for e in esims:
            esim_list.append({
                "iccid": e.iccid,
                "status": e.status,
                "country": "",
                "plan": "",
            })

        countries_data = [
            {
                "code": c.code,
                "name": c.name_ru if (user.language_code == "ru" and c.name_ru) else c.name,
                "flag": c.flag_emoji or "",
            }
            for c in all_countries
        ]

        from app.models.models import ReferralEarning
        from sqlalchemy import func, select
        result = await session.execute(
            select(func.coalesce(func.sum(ReferralEarning.amount), 0))
            .where(ReferralEarning.referrer_id == user.id)
        )
        referral_earned = float(result.scalar())

        return {
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "balance": float(user.balance),
                "total_spent": float(user.total_spent),
                "referral_earned": referral_earned,
                "referral_code": user.referral_code,
                "referral_link": f"https://t.me/{settings.BOT_USERNAME}?start={user.referral_code}",
            },
            "countries": countries_data,
            "plans": {},
            "esims": esim_list,
        }


@router.post("/tma/plans")
async def tma_plans(body: dict, request: Request):
    country_code = body.get("countryCode", "")
    if not country_code:
        raise HTTPException(400, "countryCode required")

    async with get_session() as session:
        country_repo = CountryRepository(session)
        country = await country_repo.get_by_code(country_code)
        if not country:
            raise HTTPException(404, "Country not found")

        plan_repo = PlanRepository(session)
        plans = await plan_repo.get_active_by_country(country.id)

    plans_data = [
        {
            "id": str(p.id),
            "data_gb": float(p.data_gb) if p.data_gb else 0,
            "days": p.duration_days,
            "price": str(p.final_price),
        }
        for p in plans
    ]

    return {"plans": plans_data}


@router.post("/tma/buy")
async def tma_buy(body: dict, request: Request):
    init_data = body.get("initData", "")
    plan_id = body.get("planId", "")

    verified = _verify_init_data(init_data)
    if not verified:
        raise HTTPException(401, "Invalid init data")

    tg_user = verified.get("user", {})
    telegram_id = tg_user.get("id")

    import uuid
    from app.models.models import Order

    async with get_session() as session:
        from app.repositories.repositories import UserRepository
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(404, "User not found")

        plan_repo = PlanRepository(session)
        plan = await plan_repo.get(uuid.UUID(plan_id))
        if not plan:
            raise HTTPException(404, "Plan not found")

        order_service = OrderService(session)
        order = await order_service.create_order(user.id, plan)

        nova = await get_nova_client()
        esim_service = EsimService(session, nova)
        esim = await esim_service.provision_esim(order)

        await session.commit()

        return {
            "order_id": str(order.id),
            "iccid": esim.iccid if esim else None,
            "status": "success",
        }
