from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.keyboards import admin_main_kb
from app.bot.states.states import AdminBroadcastFlow, AdminMarkupFlow
from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.esim.nova_client import get_nova_client
from app.core.cache import get_cache
from app.models.models import User
from app.repositories.repositories import (
    AdminLogRepository,
    EsimRepository,
    OrderRepository,
    PlanRepository,
    UserRepository,
)
from app.services.esim_service import CatalogService

logger = get_logger(__name__)
router = Router(name="admin")


def is_admin(user: User) -> bool:
    return user.telegram_id in settings.ADMIN_IDS


def admin_only(handler):
    """Decorator to restrict handler to admins."""
    async def wrapper(*args, **kwargs):
        user: User = kwargs.get("user") or (args[1] if len(args) > 1 else None)
        if not user or not is_admin(user):
            if args and hasattr(args[0], "answer"):
                lang = kwargs.get("lang", "en")
                await args[0].answer(t("not_admin", lang))
            elif args and hasattr(args[0], "message"):
                await args[0].answer(t("not_admin", "en"), show_alert=True)
            return
        return await handler(*args, **kwargs)
    wrapper.__name__ = handler.__name__
    return wrapper


@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message, user: User, lang: str = "en", **_) -> None:
    await message.answer(
        t("admin_panel_header", lang, name=user.first_name),
        parse_mode="HTML",
        reply_markup=admin_main_kb(lang),
    )


@router.callback_query(F.data == "admin:stats")
@admin_only
async def cb_admin_stats(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, **_) -> None:
    user_repo = UserRepository(session)
    order_repo = OrderRepository(session)
    esim_repo = EsimRepository(session)

    user_stats = await user_repo.get_stats()
    revenue_stats = await order_repo.get_revenue_stats()
    esim_count = await esim_repo.count()

    text = t(
        "admin_stats", lang,
        total_users=user_stats["total"],
        active_users=user_stats["active"],
        esims_sold=esim_count,
        today=f"{revenue_stats['today']:.2f}",
        month=f"{revenue_stats['month']:.2f}",
        total=f"{revenue_stats['total']:.2f}",
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=admin_main_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "admin:sync_catalog")
@admin_only
async def cb_sync_catalog(cb: CallbackQuery, session: AsyncSession, user: User, lang: str = "en", **_) -> None:
    await cb.answer("🔄 Syncing...")
    nova = await get_nova_client()
    cache = await get_cache()
    catalog = CatalogService(session, nova, cache)

    try:
        countries, plans = await catalog.sync_catalog()
        await cb.message.answer(
            f"✅ Sync complete!\n🌍 Countries: {countries}\n📦 Plans: {plans}",
            reply_markup=admin_main_kb(lang),
        )
    except Exception as e:
        logger.error("catalog_sync_failed", error=str(e))
        await cb.message.answer(f"❌ Sync failed: {e}")

    log_repo = AdminLogRepository(session)
    await log_repo.log(user.telegram_id, "sync_catalog")
    await session.commit()


@router.callback_query(F.data == "admin:broadcast")
@admin_only
async def cb_broadcast_start(cb: CallbackQuery, user: User, state: FSMContext, **_) -> None:
    await state.set_state(AdminBroadcastFlow.writing_message)
    await cb.message.edit_text(
        "📢 <b>Broadcast</b>\n\nSend a message to all users.\nType your message (HTML supported):",
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(AdminBroadcastFlow.writing_message)
@admin_only
async def handle_broadcast_message(message: Message, user: User, state: FSMContext, **_) -> None:
    await state.update_data(broadcast_text=message.text or message.caption or "")
    await state.set_state(AdminBroadcastFlow.confirming)

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Send", callback_data="admin:broadcast_confirm"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="admin:broadcast_cancel"),
    )
    await message.answer(
        f"📢 Preview:\n\n{message.text}\n\n<i>Send to all users?</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "admin:broadcast_confirm")
@admin_only
async def cb_broadcast_confirm(
    cb: CallbackQuery, session: AsyncSession, user: User, state: FSMContext, lang: str = "en", **_
) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    if not text:
        await cb.answer("No message to send", show_alert=True)
        return

    user_repo = UserRepository(session)
    all_users = await user_repo.get_all(limit=10000)

    sent = 0
    failed = 0
    for u in all_users:
        try:
            await cb.bot.send_message(u.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    log_repo = AdminLogRepository(session)
    await log_repo.log(user.telegram_id, "broadcast", details={"sent": sent, "failed": failed, "text_preview": text[:100]})
    await session.commit()

    await cb.message.answer(f"✅ Broadcast complete!\nSent: {sent}\nFailed: {failed}", reply_markup=admin_main_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "admin:broadcast_cancel")
@admin_only
async def cb_broadcast_cancel(cb: CallbackQuery, state: FSMContext, lang: str = "en", **_) -> None:
    await state.clear()
    await cb.message.edit_text("❌ Broadcast cancelled.", reply_markup=admin_main_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "admin:logs")
@admin_only
async def cb_admin_logs(cb: CallbackQuery, session: AsyncSession, user: User, lang: str = "en", **_) -> None:
    log_repo = AdminLogRepository(session)
    logs = await log_repo.get_recent(20)

    if not logs:
        await cb.answer("No logs yet", show_alert=True)
        return

    lines = ["📋 <b>Recent Admin Logs</b>\n"]
    for log in logs:
        dt = log.created_at.strftime("%m-%d %H:%M")
        lines.append(f"• [{dt}] <code>{log.action}</code> by {log.admin_telegram_id}")

    await cb.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=admin_main_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "admin:users")
@admin_only
async def cb_admin_users(cb: CallbackQuery, session: AsyncSession, user: User, **_) -> None:
    user_repo = UserRepository(session)
    stats = await user_repo.get_stats()
    recent = await user_repo.get_all(limit=10)

    lines = [f"👥 <b>Users</b>\n\nTotal: {stats['total']} | Active: {stats['active']}\n"]
    for u in recent:
        name = f"@{u.username}" if u.username else u.first_name
        lines.append(f"• {name} ({u.telegram_id}) — ${u.total_spent:.2f}")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    await cb.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())
    await cb.answer()


@router.callback_query(F.data == "admin:main")
@admin_only
async def cb_admin_main(cb: CallbackQuery, user: User, lang: str = "en", **_) -> None:
    await cb.message.edit_text(
        t("admin_panel_header", lang, name=user.first_name),
        parse_mode="HTML",
        reply_markup=admin_main_kb(lang),
    )
    await cb.answer()


@router.callback_query(F.data == "menu:admin")
@admin_only
async def cb_menu_admin(cb: CallbackQuery, user: User, lang: str = "en", **_) -> None:
    await cb.message.edit_text(
        t("admin_panel_header", lang, name=user.first_name),
        parse_mode="HTML",
        reply_markup=admin_main_kb(lang),
    )
    await cb.answer()
