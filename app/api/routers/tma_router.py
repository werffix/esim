import hashlib
import hmac
import json
import uuid
import urllib.parse
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import settings
from app.esim.nova_client import get_nova_client
from app.models.models import ReferralEarning, User
from app.repositories.repositories import CountryRepository, EsimRepository, PlanRepository, UserRepository
from app.services.esim_service import CatalogService, EsimService, OrderService
from app.db.database import get_session

router = APIRouter(tags=["tma"])

COUNTRY_NAMES_RU: dict[str, str] = {
    "JP": "Япония", "CN": "Китай", "AU": "Австралия", "KR": "Республика Корея",
    "MY": "Малайзия", "US": "Соединенные Штаты", "TH": "Таиланд", "CA": "Канада",
    "ID": "Индонезия", "SG": "Сингапур", "VN": "Вьетнам", "MO": "Макао",
    "HK": "Гонконг", "AE": "ОАЭ", "GR": "Греция", "TR": "Турция",
    "CH": "Швейцария", "PH": "Филиппины", "FR": "Франция", "GB": "Великобритания",
    "KE": "Кения", "RE": "Реюньон", "MA": "Марокко", "NZ": "Новая Зеландия",
    "BR": "Бразилия", "DE": "Германия", "PT": "Португалия", "ZA": "Южно-Африканская Республика",
    "NL": "Нидерланды", "PA": "Панама", "BG": "Болгария", "EG": "Египет",
    "MX": "Мексика", "ES": "Испания", "DZ": "Алжир", "DK": "Дания",
    "LK": "Шри-Ланка", "AT": "Австрия", "SN": "Сенегал", "IE": "Ирландия",
    "IT": "Италия", "IN": "Индия", "CZ": "Чехия", "GU": "Гуам",
    "LU": "Люксембург", "KW": "Кувейт", "SI": "Словения", "IS": "Исландия",
    "JO": "Иордания", "PL": "Польша", "IL": "Израиль", "LA": "Лаос",
    "HR": "Хорватия", "EE": "Эстония", "BE": "Бельгия", "LT": "Литва",
    "TN": "Тунис", "QA": "Катар", "RO": "Румыния", "CY": "Кипр",
    "NO": "Норвегия", "HU": "Венгрия", "FI": "Финляндия", "IQ": "Ирак",
    "NE": "Нигер", "MK": "Северная Македония", "TD": "Чад", "MD": "Молдова",
    "GA": "Габон", "FO": "Фарерские о-ва", "MW": "Малави", "PF": "Французская Полинезия",
    "SZ": "Эсватини", "SC": "Сейшельские о-ва", "UA": "Украина", "BA": "Босния и Герцеговина",
    "BH": "Бахрейн", "AL": "Албания", "SE": "Швеция", "GF": "Французская Гвиана",
    "NP": "Непал", "PE": "Перу", "ZM": "Замбия", "AZ": "Азербайджан",
    "UZ": "Узбекистан", "RS": "Сербия", "HN": "Гондурас", "PY": "Парагвай",
    "SA": "Саудовская Аравия", "AM": "Армения", "NI": "Никарагуа", "AR": "Аргентина",
    "GE": "Грузия", "KH": "Камбоджа", "KZ": "Казахстан", "CO": "Колумбия",
    "DO": "Доминиканская Республика", "PK": "Пакистан", "UY": "Уругвай", "CL": "Чили",
    "LV": "Латвия", "LI": "Лихтенштейн", "SK": "Словакия", "BD": "Бангладеш",
    "GT": "Гватемала", "OM": "Оман", "NG": "Нигерия", "UG": "Уганда",
    "ME": "Черногория", "FJ": "Фиджи", "RU": "Россия", "BB": "Барбадос",
    "SM": "Сан-Марино", "MU": "Маврикий", "SR": "Суринам", "CW": "Кюрасао",
    "TZ": "Танзания", "YT": "Майотта", "CV": "Кабо-Верде", "MQ": "Мартиника",
    "MT": "Мальта", "BW": "Ботсвана", "BJ": "Бенин", "GP": "Гваделупа",
    "GH": "Гана", "AD": "Андорра", "TJ": "Таджикистан", "VA": "Ватикан",
    "BT": "Бутан", "BL": "Сен-Бартелеми", "KG": "Киргизия", "BY": "Беларусь",
    "HT": "Гаити", "EC": "Эквадор", "GY": "Гайана", "MF": "Сен-Мартен",
    "DM": "Доминика", "GM": "Гамбия", "SL": "Сьерра-Леоне", "LY": "Ливия",
    "AI": "Ангилья", "AX": "Аландские о-ва", "BF": "Буркина-Фасо", "JE": "Джерси",
    "AG": "Антигуа и Барбуда", "KY": "о-ва Кайман", "CG": "Конго - Браззавиль",
    "GW": "Гвинея-Бисау", "GI": "Гибралтар", "AF": "Афганистан", "MC": "Монако",
    "CR": "Коста-Рика", "BM": "Бермудские о-ва", "CM": "Камерун", "BS": "Багамы",
    "IM": "о-в Мэн", "KN": "Сент-Китс и Невис", "VG": "Виргинские о-ва (Великобритания)",
    "GN": "Гвинея", "MV": "Мальдивы", "BZ": "Белиз", "RW": "Руанда",
    "TC": "Тёркс и Кайкос", "BN": "Бруней", "MS": "Монтсеррат", "LC": "Сент-Люсия",
    "TT": "Тринидад и Тобаго", "WS": "Самоа", "GD": "Гренада",
    "VC": "Сент-Винсент и Гренадины", "AO": "Ангола", "CD": "Конго - Киншаса",
    "GL": "Гренландия", "MN": "Монголия", "BO": "Боливия", "JM": "Ямайка",
    "CI": "Кот-д'Ивуар", "SV": "Сальвадор", "MZ": "Мозамбик", "GG": "Гернси",
    "MG": "Мадагаскар", "LR": "Либерия", "PR": "Пуэрто-Рико", "SD": "Судан",
    "CF": "Центрально-Африканская Республика", "ML": "Мали",
}


def _verify_init_data(init_data: str) -> dict[str, Any] | None:
    if not init_data:
        return None
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


def _country_name(c: Any, lang: str = "ru") -> str:
    name = COUNTRY_NAMES_RU.get(c.code)
    if name:
        return name
    return c.name_ru if (lang == "ru" and c.name_ru) else c.name


@router.get("/tma")
async def serve_tma(request: Request):
    with open("app/static/tma.html") as f:
        return HTMLResponse(f.read())


@router.post("/tma/init")
async def tma_init(body: dict, request: Request):
    init_data = body.get("initData", "")
    verified = _verify_init_data(init_data)

    async with get_session() as session:
        if verified:
            tg_user = verified.get("user", {})
            telegram_id = tg_user.get("id")
            lang = tg_user.get("language_code", "ru")

            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)

            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=tg_user.get("username"),
                    first_name=tg_user.get("first_name", ""),
                    last_name=tg_user.get("last_name", ""),
                    language_code=lang,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
        else:
            lang = "ru"
            user = None

        nova = await get_nova_client()
        cache = await get_cache()
        catalog = CatalogService(session, nova, cache)
        all_countries = await catalog.get_active_countries()

        esim_list = []
        if user:
            from app.models.models import Country as CountryModel, Order as OrderModel, Plan as PlanModel
            esim_repo = EsimRepository(session)
            esims = await esim_repo.get_user_esims(user.id)
            for e in esims:
                country_name = ""
                plan_name = ""
                if e.order_id:
                    order = await session.get(OrderModel, e.order_id)
                    if order and order.plan_id:
                        plan = await session.get(PlanModel, order.plan_id)
                        if plan:
                            plan_name = plan.name or f"{plan.data_gb}GB/{plan.duration_days}d"
                            country_obj = await session.get(CountryModel, plan.country_id)
                            if country_obj:
                                country_name = COUNTRY_NAMES_RU.get(country_obj.code, country_obj.name)
                esim_list.append({
                    "iccid": e.iccid,
                    "status": e.status,
                    "country": country_name,
                    "plan": plan_name,
                    "qr_code_data": e.qr_code_data,
                    "qr_code_url": e.qr_code_url,
                    "activation_code": e.activation_code,
                })

        countries_data = [
            {
                "code": c.code,
                "name": _country_name(c, lang),
                "flag": c.flag_emoji or "",
            }
            for c in all_countries
        ]

        user_data = None
        if user:
            result = await session.execute(
                select(func.coalesce(func.sum(ReferralEarning.amount), 0))
                .where(ReferralEarning.referrer_id == user.id)
            )
            referral_earned = float(result.scalar())
            user_data = {
                "id": str(user.id),
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "balance": float(user.balance),
                "total_spent": float(user.total_spent),
                "referral_earned": referral_earned,
                "referral_code": user.referral_code,
                "referral_link": f"https://t.me/{settings.BOT_USERNAME}?start={user.referral_code}",
                "is_admin": user.telegram_id in settings.ADMIN_IDS,
            }

        return {
            "user": user_data,
            "countries": countries_data,
            "plans": {},
            "esims": esim_list,
        }


@router.post("/tma/plans")
async def tma_plans(body: dict):
    country_code = body.get("countryCode", "")
    if not country_code:
        raise HTTPException(400, "countryCode required")

    async with get_session() as session:
        country_repo = CountryRepository(session)
        country = await country_repo.get_by_code(country_code)
        if not country:
            raise HTTPException(404, "Country not found")

        plan_repo = PlanRepository(session)
        plans = await plan_repo.get_by_country(country.id)

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
async def tma_buy(body: dict):
    init_data = body.get("initData", "")
    plan_id = body.get("planId", "")

    verified = _verify_init_data(init_data)
    if not verified:
        raise HTTPException(401, "Требуется авторизация через Telegram")

    tg_user = verified.get("user", {})
    telegram_id = tg_user.get("id")

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        plan_repo = PlanRepository(session)
        plan = await plan_repo.get(uuid.UUID(plan_id))
        if not plan:
            raise HTTPException(404, "Тариф не найден")

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
