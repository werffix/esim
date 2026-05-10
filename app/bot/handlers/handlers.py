import uuid
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.keyboards import (
    back_kb,
    countries_kb,
    esim_detail_kb,
    esim_list_kb,
    language_kb,
    main_menu_kb,
    order_confirm_kb,
    payment_kb,
    plans_kb,
)
from app.bot.states.states import BuyFlow, SupportFlow
from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.esim.nova_client import get_nova_client
from app.core.cache import get_cache
from app.models.models import User
from app.payments.platega import platega_client
from app.repositories.repositories import (
    CountryRepository,
    EsimRepository,
    OrderRepository,
    PlanRepository,
    UserRepository,
)
from app.services.esim_service import CatalogService, EsimService, OrderService

logger = get_logger(__name__)

router = Router(name="main")

LOGO_PATH = "/app/q1es.png"


def _read_logo() -> BufferedInputFile:
    with open(LOGO_PATH, "rb") as f:
        return BufferedInputFile(f.read(), filename="q1es.png")


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, user: User, lang: str, state: FSMContext) -> None:
    await state.clear()
    is_admin = user.telegram_id in settings.ADMIN_IDS
    reply_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 " + t("menu_main", lang))]],
        resize_keyboard=True,
        is_persistent=True,
    )
    await message.answer_photo(
        _read_logo(),
        caption=t("welcome", lang),
        parse_mode="HTML",
        reply_markup=reply_kb,
    )
    await message.answer(
        t("choose_action", lang),
        reply_markup=main_menu_kb(lang, is_admin=is_admin),
    )


@router.callback_query(F.data == "menu:start")
async def cb_menu_start(cb: CallbackQuery, user: User, lang: str, state: FSMContext) -> None:
    await state.clear()
    is_admin = user.telegram_id in settings.ADMIN_IDS
    await cb.message.edit_text(
        t("choose_action", lang),
        parse_mode="HTML",
        reply_markup=main_menu_kb(lang, is_admin=is_admin),
    )
    await cb.answer()


@router.message(Command("shop"))
async def cmd_shop(message: Message, user: User, lang: str) -> None:
    from aiogram.types import InlineKeyboardButton, WebAppInfo
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t("menu_open_app", lang),
        web_app=WebAppInfo(url="https://app.q1esim.site/tma"),
    ))
    await message.answer(t("welcome", lang), parse_mode="HTML", reply_markup=builder.as_markup())


@router.message(F.text.in_(["📋 Главное меню", "📋 Main Menu"]))
async def msg_main_menu(message: Message, user: User, lang: str, state: FSMContext) -> None:
    await state.clear()
    is_admin = user.telegram_id in settings.ADMIN_IDS
    await message.answer(
        t("choose_action", lang),
        reply_markup=main_menu_kb(lang, is_admin=is_admin),
    )


# ─── Buy flow ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:buy")
async def cb_buy(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext) -> None:
    await state.clear()
    await cb.answer(t("loading", lang))

    nova = await get_nova_client()
    cache = await get_cache()
    catalog = CatalogService(session, nova, cache)
    countries = await catalog.get_active_countries()

    if not countries:
        await cb.message.edit_text(t("no_countries", lang), parse_mode="HTML")
        return

    await state.set_state(BuyFlow.selecting_country)
    await state.update_data(countries_page=0)

    await cb.message.edit_text(
        t("select_country", lang),
        parse_mode="HTML",
        reply_markup=countries_kb(countries, lang, page=0),
    )


@router.callback_query(F.data.startswith("countries_page:"))
async def cb_countries_page(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext) -> None:
    page = int(cb.data.split(":")[1])
    nova = await get_nova_client()
    cache = await get_cache()
    catalog = CatalogService(session, nova, cache)
    countries = await catalog.get_active_countries()
    await state.update_data(countries_page=page)
    await cb.message.edit_reply_markup(reply_markup=countries_kb(countries, lang, page=page))
    await cb.answer()


@router.callback_query(F.data.startswith("country:"))
async def cb_country(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext) -> None:
    country_code = cb.data.split(":")[1]
    repo = CountryRepository(session)
    country = await repo.get_by_code(country_code)

    if not country:
        await cb.answer(t("country_not_found", lang), show_alert=True)
        return

    plan_repo = PlanRepository(session)
    plans = await plan_repo.get_by_country(country.id)

    if not plans:
        await cb.answer(t("no_plans", lang), show_alert=True)
        return

    await state.set_state(BuyFlow.selecting_plan)
    await state.update_data(country_id=str(country.id), country_code=country_code, plans_page=0)

    flag = country.flag_emoji or "🌐"
    name = country.name_ru if (lang == "ru" and country.name_ru) else country.name

    await cb.message.edit_text(
        t("select_plan", lang, country=name, flag=flag),
        parse_mode="HTML",
        reply_markup=plans_kb(plans, lang),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("plans_page:"))
async def cb_plans_page(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext) -> None:
    page = int(cb.data.split(":")[1])
    data = await state.get_data()
    country_id = uuid.UUID(data["country_id"])
    plan_repo = PlanRepository(session)
    plans = await plan_repo.get_by_country(country_id)
    await state.update_data(plans_page=page)
    await cb.message.edit_reply_markup(reply_markup=plans_kb(plans, lang, page=page))
    await cb.answer()


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext) -> None:
    plan_id = uuid.UUID(cb.data.split(":")[1])
    plan_repo = PlanRepository(session)
    plan = await plan_repo.get(plan_id)

    if not plan:
        await cb.answer("Plan not found", show_alert=True)
        return

    country_repo = CountryRepository(session)
    country = await country_repo.get(plan.country_id)

    await state.set_state(BuyFlow.confirming_order)
    await state.update_data(plan_id=str(plan_id))

    country_name = country.name if country else "Unknown"
    flag = (country.flag_emoji or "🌐") if country else "🌐"
    amount = str(plan.final_price)

    order_service = OrderService(session)
    order = await order_service.create_order(user.id, plan.id)

    await state.update_data(order_id=str(order.id))

    text = t(
        "order_confirm", lang,
        country=f"{flag} {country_name}",
        plan=plan.name,
        data_gb=plan.data_gb,
        days=plan.duration_days,
        amount=amount,
    )
    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=order_confirm_kb(order.id, amount, lang),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext) -> None:
    order_id = uuid.UUID(cb.data.split(":")[1])
    order_repo = OrderRepository(session)
    order = await order_repo.get(order_id)

    if not order or order.user_id != user.id:
        await cb.answer("Order not found", show_alert=True)
        return

    if order.status != "pending":
        await cb.answer("Order already processed", show_alert=True)
        return

    from app.payments.platega import PlategaPayment
    from app.repositories.repositories import PaymentRepository

    # Sandbox mode — skip real payment, auto-provision
    if settings.APP_ENV != "production":
        fake_id = f"sandbox_{uuid.uuid4().hex[:16]}"
        payment = PlategaPayment(
            payment_id=fake_id,
            payment_url=f"{settings.APP_BASE_URL}/webhook/sandbox-confirm/{fake_id}",
            status="success",
            amount=order.amount,
            currency=order.currency,
            external_ref=order.external_ref,
        )
        await cb.message.edit_text("⏳ Processing sandbox payment...")
        await cb.answer()

        # Save payment
        payment_repo = PaymentRepository(session)
        await payment_repo.create(
            order_id=order.id,
            platega_payment_id=payment.payment_id,
            amount=order.amount,
            currency=order.currency,
            status="success",
            payment_url=payment.payment_url,
        )
        await order_repo.update_status(order.id, "paid", payment_id=payment.payment_id, payment_url=payment.payment_url)
        await session.commit()

        # Provision eSIM
        from app.esim.nova_client import get_nova_client
        nova = await get_nova_client()
        esim_service = EsimService(session, nova)
        try:
            esim = await esim_service.provision_esim(order)
            await cb.message.edit_text(
                t("esim_ready", lang, iccid=esim.iccid, activation_code=esim.activation_code or "N/A", lpa=esim.lpa or "N/A"),
                parse_mode="HTML",
            )
            if esim.qr_code_data:
                import base64
                qr_bytes = base64.b64decode(esim.qr_code_data)
                await cb.message.answer_photo(BufferedInputFile(qr_bytes, "esim_qr.png"), caption="📸 Scan to activate your eSIM")
            elif esim.qr_code_url:
                await cb.message.answer_photo(esim.qr_code_url, caption="📸 Scan to activate your eSIM")
        except Exception as exc:
            logger.error("sandbox_provision_failed", order_id=str(order.id), error=str(exc), exc_info=True)
            await cb.message.edit_text("❌ Provisioning failed. Check logs.")
        return

    # Production mode — real Platega
    try:
        payment = await platega_client.create_payment(
            amount=order.amount,
            currency=order.currency,
            external_ref=order.external_ref,
            description=f"Q1 eSIM Order #{order.external_ref}",
            customer_telegram_id=user.telegram_id,
        )
    except Exception as exc:
        logger.error("payment_creation_failed", order_id=str(order_id), error=str(exc), exc_info=True)
        await cb.answer(t("error_generic", lang), show_alert=True)
        return

    # Save payment info
    payment_repo = PaymentRepository(session)
    await payment_repo.create(
        order_id=order.id,
        platega_payment_id=payment.payment_id,
        amount=order.amount,
        currency=order.currency,
        status="pending",
        payment_url=payment.payment_url,
    )
    await order_repo.update_status(order.id, "pending", payment_id=payment.payment_id, payment_url=payment.payment_url)
    await session.commit()

    await state.set_state(BuyFlow.awaiting_payment)

    await cb.message.edit_text(
        t("payment_created", lang),
        parse_mode="HTML",
        reply_markup=payment_kb(payment.payment_url, lang),
    )
    await cb.answer()


# ─── My eSIMs ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:my_esims")
async def cb_my_esims(cb: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    nova = await get_nova_client()
    esim_service = EsimService(session, nova)
    esims = await esim_service.get_user_esims(user.id)

    if not esims:
        await cb.message.edit_text(
            t("my_esims_empty", lang),
            parse_mode="HTML",
            reply_markup=back_kb("menu:start", lang),
        )
        await cb.answer()
        return

    await cb.message.edit_text(
        t("my_esims_header", lang, count=len(esims)),
        parse_mode="HTML",
        reply_markup=esim_list_kb(esims, lang),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("esim:"))
async def cb_esim_detail(cb: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    iccid = cb.data.split(":", 1)[1]
    repo = EsimRepository(session)
    esim = await repo.get_by_iccid(iccid)

    if not esim or esim.user_id != user.id:
        await cb.answer("eSIM not found", show_alert=True)
        return

    from app.repositories.repositories import PlanRepository, OrderRepository
    order = await OrderRepository(session).get(esim.order_id)
    plan = await PlanRepository(session).get(order.plan_id) if order else None
    from app.repositories.repositories import CountryRepository
    country = await CountryRepository(session).get(plan.country_id) if plan else None

    status_key = f"esim_status_{esim.status}" if esim.status in ("active", "inactive", "expired") else "esim_status_inactive"
    expires = esim.expires_at.strftime("%Y-%m-%d") if esim.expires_at else "N/A"

    text = t(
        "esim_detail", lang,
        iccid=esim.iccid,
        country=f"{country.flag_emoji or ''} {country.name}" if country else "N/A",
        plan=plan.name if plan else "N/A",
        status=t(status_key, lang),
        used_mb=esim.data_used_mb or 0,
        total_mb=esim.data_total_mb or 0,
        expires_at=expires,
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=esim_detail_kb(iccid, lang))
    await cb.answer()


@router.callback_query(F.data.startswith("esim_qr:"))
async def cb_esim_qr(cb: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    iccid = cb.data.split(":", 1)[1]
    repo = EsimRepository(session)
    esim = await repo.get_by_iccid(iccid)

    if not esim or esim.user_id != user.id:
        await cb.answer("eSIM not found", show_alert=True)
        return

    await cb.answer()

    if esim.qr_code_data:
        import base64
        qr_bytes = base64.b64decode(esim.qr_code_data)
        await cb.message.answer_photo(
            BufferedInputFile(qr_bytes, filename="esim_qr.png"),
            caption=f"📱 QR for ICCID: <code>{iccid}</code>",
            parse_mode="HTML",
        )
    elif esim.qr_code_url:
        await cb.message.answer_photo(
            esim.qr_code_url,
            caption=f"📱 QR for ICCID: <code>{iccid}</code>",
            parse_mode="HTML",
        )
    else:
        # Try fetching from Nova
        nova = await get_nova_client()
        try:
            qr = await nova.get_esim_qr(iccid)
            if qr.qr_base64:
                import base64
                qr_bytes = base64.b64decode(qr.qr_base64)
                await cb.message.answer_photo(
                    BufferedInputFile(qr_bytes, filename="esim_qr.png"),
                    caption=f"📱 ICCID: <code>{iccid}</code>",
                    parse_mode="HTML",
                )
        except Exception:
            await cb.message.answer("❌ QR code not available yet.")


@router.callback_query(F.data.startswith("esim_refresh:"))
async def cb_esim_refresh(cb: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    iccid = cb.data.split(":", 1)[1]
    repo = EsimRepository(session)
    esim = await repo.get_by_iccid(iccid)

    if not esim or esim.user_id != user.id:
        await cb.answer("eSIM not found", show_alert=True)
        return

    nova = await get_nova_client()
    esim_service = EsimService(session, nova)
    esim = await esim_service.refresh_esim_status(esim)

    await cb.answer("✅ Status updated!")
    # Re-render detail view
    await cb_esim_detail(cb, session, user, lang)


# ─── Profile ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:profile")
async def cb_profile(cb: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    esim_repo = EsimRepository(session)
    esims = await esim_repo.get_user_esims(user.id)

    since = user.created_at.strftime("%Y-%m-%d")
    name = f"{user.first_name} {user.last_name or ''}".strip()

    text = t(
        "profile", lang,
        telegram_id=user.telegram_id,
        name=name,
        balance=f"{user.balance:.2f}",
        total_spent=f"{user.total_spent:.2f}",
        esim_count=len(esims),
        since=since,
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb("menu:start", lang))
    await cb.answer()


# ─── Referral ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:referral")
async def cb_referral(cb: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    from app.services.user_service import UserService
    user_service = UserService(session)
    stats = await user_service.get_referral_stats(user.id)

    bot_info = await cb.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.referral_code}"

    text = t(
        "referral", lang,
        percent=settings.REFERRAL_PERCENT,
        link=ref_link,
        count=stats["referral_count"],
        earned=f"{stats['total_earned']:.2f}",
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb("menu:start", lang))
    await cb.answer()


# ─── Language ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:language")
async def cb_language(cb: CallbackQuery, user: User, lang: str) -> None:
    await cb.message.edit_text(
        "🌐 Choose your language / Выберите язык:",
        reply_markup=language_kb(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    lang_code = cb.data.split(":")[1]
    if lang_code not in ("en", "ru"):
        await cb.answer("Invalid language", show_alert=True)
        return
    user.language_code = lang_code
    await session.commit()
    await cb.answer("✅")
    is_admin = user.telegram_id in settings.ADMIN_IDS
    await cb.message.edit_text(
        t("welcome", lang_code),
        parse_mode="HTML",
        reply_markup=main_menu_kb(lang_code, is_admin=is_admin),
    )


# ─── Support ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:support")
async def cb_support(cb: CallbackQuery, user: User, lang: str, state: FSMContext) -> None:
    await state.set_state(SupportFlow.writing_message)
    await cb.message.edit_text(
        t("support_message", lang),
        parse_mode="HTML",
        reply_markup=back_kb("menu:start", lang),
    )
    await cb.answer()


@router.message(SupportFlow.writing_message)
async def handle_support_message(message: Message, user: User, lang: str, state: FSMContext) -> None:
    # Forward to admin group or admins
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"📨 Support message from {user.first_name} (@{user.username}, #{user.telegram_id}):\n\n{message.text}",
            )
        except Exception:
            pass

    await state.clear()
    await message.answer(t("support_sent", lang), parse_mode="HTML", reply_markup=main_menu_kb(lang))


# ─── Noop ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()
