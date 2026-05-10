import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update

from app.core.config import settings
from app.db.database import get_session
from app.models.models import Country, Plan
from app.repositories.repositories import CountryRepository, PlanRepository

router = APIRouter(prefix="/tma/admin", tags=["tma_admin"])


def _is_admin(request: Request) -> bool:
    telegram_id = request.state.get("telegram_id") or getattr(request, "_test_admin_id", None)
    return telegram_id in settings.ADMIN_IDS


@router.put("/country/{code}")
async def update_country(code: str, body: dict, request: Request):
    description = body.get("description", "")
    sort_order = body.get("sort_order")
    async with get_session() as session:
        repo = CountryRepository(session)
        country = await repo.get_by_code(code)
        if not country:
            raise HTTPException(404, "Country not found")
        if description is not None:
            country.description = description
        if sort_order is not None:
            country.sort_order = int(sort_order)
        await session.commit()
        return {"status": "ok"}


@router.post("/country/bulk-description")
async def bulk_set_country_description(body: dict, request: Request):
    description = body.get("description", "")
    async with get_session() as session:
        await session.execute(update(Country).values(description=description))
        await session.commit()
        return {"status": "ok"}


@router.get("/countries")
async def list_countries_for_admin(request: Request):
    async with get_session() as session:
        repo = CountryRepository(session)
        from app.esim.nova_client import get_nova_client
        from app.core.cache import get_cache
        from app.services.esim_service import CatalogService
        nova = await get_nova_client()
        cache = await get_cache()
        catalog = CatalogService(session, nova, cache)
        all_countries = await catalog.get_active_countries()
        return [{
            "code": c.code,
            "name": c.name,
            "name_ru": c.name_ru or "",
            "sort_order": c.sort_order,
            "description": c.description or "",
        } for c in sorted(all_countries, key=lambda x: x.sort_order)]


@router.post("/plan-markup")
async def apply_plan_markup(body: dict, request: Request):
    markup_percent = body.get("markup_percent")
    if markup_percent is None or not isinstance(markup_percent, (int, float)):
        raise HTTPException(400, "markup_percent required (number)")
    async with get_session() as session:
        await session.execute(update(Plan).values(markup_percent=float(markup_percent)))
        await session.commit()
        return {"status": "ok"}


@router.get("/plans")
async def list_plans_for_admin(request: Request):
    async with get_session() as session:
        repo = PlanRepository(session)
        from app.esim.nova_client import get_nova_client
        from app.core.cache import get_cache
        from app.services.esim_service import CatalogService
        nova = await get_nova_client()
        cache = await get_cache()
        catalog = CatalogService(session, nova, cache)
        all_countries = await catalog.get_active_countries()
        result = []
        for c in all_countries:
            plans = await repo.get_by_country(c.id)
            for p in plans:
                result.append({
                    "id": str(p.id),
                    "name": p.name,
                    "data_gb": float(p.data_gb),
                    "days": p.duration_days,
                    "base_price": float(p.base_price),
                    "markup_percent": float(p.markup_percent),
                    "final_price": float(p.final_price),
                    "country_code": c.code,
                    "country_name": c.name,
                })
        return {"plans": result}
