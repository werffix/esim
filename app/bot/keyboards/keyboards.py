import uuid
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.i18n import t
from app.models.models import Country, Esim, Plan


def main_menu_kb(lang: str = "en", is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🛍️ " + t("menu_open_app", lang),
        web_app=WebAppInfo(url="https://app.q1esim.site/tma"),
    ))
    builder.row(InlineKeyboardButton(text=t("menu_buy", lang), callback_data="menu:buy"))
    builder.row(InlineKeyboardButton(text=t("menu_my_esims", lang), callback_data="menu:my_esims"))
    builder.row(
        InlineKeyboardButton(text=t("menu_profile", lang), callback_data="menu:profile"),
        InlineKeyboardButton(text=t("menu_referral", lang), callback_data="menu:referral"),
    )
    builder.row(
        InlineKeyboardButton(text=t("menu_support", lang), callback_data="menu:support"),
        InlineKeyboardButton(text=t("menu_language", lang), callback_data="menu:language"),
    )
    if is_admin:
        builder.row(InlineKeyboardButton(text=t("menu_admin", lang), callback_data="menu:admin"))
    return builder.as_markup()


def countries_kb(countries: list[Country], lang: str = "en", page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    start = page * page_size
    end = start + page_size
    page_countries = countries[start:end]
    total_pages = (len(countries) + page_size - 1) // page_size

    for country in page_countries:
        flag = country.flag_emoji or "🌐"
        name = country.name_ru if (lang == "ru" and country.name_ru) else country.name
        builder.row(
            InlineKeyboardButton(
                text=f"{flag} {name}",
                callback_data=f"country:{country.code}",
            )
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"countries_page:{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"countries_page:{page+1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data="menu:buy_back"))
    return builder.as_markup()


def plans_kb(plans: list[Plan], lang: str = "en", page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    start = page * page_size
    end = start + page_size
    page_plans = plans[start:end]
    total_pages = (len(plans) + page_size - 1) // page_size

    for plan in page_plans:
        label = f"📦 {plan.data_gb}GB · {plan.duration_days}d · ${plan.final_price}"
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"plan:{plan.id}")
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"plans_page:{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"plans_page:{page+1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data="menu:buy"))
    return builder.as_markup()


def order_confirm_kb(order_id: uuid.UUID, amount: str, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("btn_pay", lang, amount=amount),
            callback_data=f"pay:{order_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="menu:buy")
    )
    return builder.as_markup()


def payment_kb(payment_url: str, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_pay_now", lang), url=payment_url))
    return builder.as_markup()


def esim_list_kb(esims: list[Esim], lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for esim in esims:
        status_icon = "🟢" if esim.status == "active" else ("⚫" if esim.status == "expired" else "🔴")
        label = f"{status_icon} {esim.iccid[-8:]}"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"esim:{esim.iccid}"))
    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data="menu:start"))
    return builder.as_markup()


def esim_detail_kb(iccid: str, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("btn_show_qr", lang), callback_data=f"esim_qr:{iccid}"),
        InlineKeyboardButton(text=t("btn_check_status", lang), callback_data=f"esim_refresh:{iccid}"),
    )
    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data="menu:my_esims"))
    return builder.as_markup()


def language_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
    )
    return builder.as_markup()


def back_kb(callback: str = "menu:start", lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data=callback))
    return builder.as_markup()


# ─── Admin keyboards ──────────────────────────────────────────────────────────

def admin_main_kb(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("admin_btn_stats", lang), callback_data="admin:stats"))
    builder.row(
        InlineKeyboardButton(text=t("admin_btn_users", lang), callback_data="admin:users"),
        InlineKeyboardButton(text=t("admin_btn_esims", lang), callback_data="admin:esims"),
    )
    builder.row(
        InlineKeyboardButton(text=t("admin_btn_countries", lang), callback_data="admin:countries"),
        InlineKeyboardButton(text=t("admin_btn_plans", lang), callback_data="admin:plans"),
    )
    builder.row(
        InlineKeyboardButton(text=t("admin_btn_broadcast", lang), callback_data="admin:broadcast"),
        InlineKeyboardButton(text=t("admin_btn_logs", lang), callback_data="admin:logs"),
    )
    builder.row(InlineKeyboardButton(text=t("admin_btn_sync", lang), callback_data="admin:sync_catalog"))
    builder.row(InlineKeyboardButton(text=t("admin_btn_exit", lang), callback_data="menu:start"))
    return builder.as_markup()


def admin_markup_kb(plans: list[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans[:10]:
        builder.row(InlineKeyboardButton(
            text=f"📦 {plan.nova_plan_id} ({plan.markup_percent}%)",
            callback_data=f"admin:set_markup:{plan.id}",
        ))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:plans"))
    return builder.as_markup()
