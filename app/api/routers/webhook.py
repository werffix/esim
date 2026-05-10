import json
from datetime import datetime

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import AsyncSessionLocal
from app.esim.nova_client import get_nova_client
from app.models.models import Order
from app.payments.platega import platega_client
from app.repositories.repositories import EsimRepository, OrderRepository, PaymentRepository
from app.services.esim_service import EsimService, OrderService

logger = get_logger(__name__)
router = APIRouter()


@router.post(settings.BOT_WEBHOOK_PATH)
async def bot_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(None)) -> Response:
    """Telegram webhook endpoint."""
    if x_telegram_bot_api_secret_token != settings.BOT_WEBHOOK_SECRET:
        logger.warning("invalid_webhook_secret")
        raise HTTPException(status_code=403, detail="Forbidden")

    bot = request.app.state.bot
    dp = request.app.state.dp

    body = await request.body()
    update = Update.model_validate_json(body)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)


@router.post(settings.PLATEGA_WEBHOOK_PATH)
async def payment_webhook(request: Request, x_platega_signature: str = Header(None, alias="X-Platega-Signature")) -> dict:
    """Platega payment webhook."""
    raw_body = await request.body()

    if not x_platega_signature:
        logger.warning("missing_payment_signature")
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        payload = platega_client.parse_webhook(raw_body, x_platega_signature)
    except ValueError as e:
        logger.warning("invalid_payment_signature", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info(
        "payment_webhook_received",
        payment_id=payload.payment_id,
        external_ref=payload.external_ref,
        status=payload.status,
    )

    async with AsyncSessionLocal() as session:
        try:
            await _process_payment_webhook(session, payload, request.app.state.bot)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("payment_webhook_processing_failed", error=str(exc), exc_info=True)
            raise HTTPException(status_code=500, detail="Processing failed")

    return {"ok": True}


async def _process_payment_webhook(session: AsyncSession, payload, bot) -> None:
    from app.payments.platega import PlategaWebhookPayload

    payment_repo = PaymentRepository(session)
    order_repo = OrderRepository(session)

    # Find payment by platega ID
    payment = await payment_repo.get_by_platega_id(payload.payment_id)
    if not payment:
        logger.warning("payment_not_found", payment_id=payload.payment_id)
        return

    if payment.status == "success":
        logger.info("payment_already_processed", payment_id=payload.payment_id)
        return

    paid_at = None
    if payload.paid_at:
        from dateutil.parser import parse
        paid_at = parse(payload.paid_at)

    # Update payment record
    await payment_repo.update_status(
        payment.id,
        status=payload.status,
        webhook_data={"payment_id": payload.payment_id, "status": payload.status},
        paid_at=paid_at,
    )

    if payload.status != "success":
        logger.info("payment_not_successful", status=payload.status)
        order = await order_repo.get(payment.order_id)
        if order:
            await order_repo.update_status(order.id, "failed" if payload.status == "failed" else "pending")
        return

    # Mark order as paid
    order_service = OrderService(session)
    order = await order_service.mark_paid(
        external_ref=payload.external_ref,
        payment_id=payload.payment_id,
        paid_at=paid_at or datetime.utcnow(),
    )

    if not order:
        logger.error("order_not_found_for_payment", external_ref=payload.external_ref)
        return

    # Provision eSIM
    nova = await get_nova_client()
    esim_service = EsimService(session, nova)

    try:
        esim = await esim_service.provision_esim(order)
        await _notify_user_esim_ready(bot, session, order, esim)
    except Exception as exc:
        logger.error("esim_provisioning_failed", order_id=str(order.id), error=str(exc))
        await _notify_user_esim_failed(bot, order)


async def _notify_user_esim_ready(bot, session: AsyncSession, order: Order, esim) -> None:
    from app.repositories.repositories import UserRepository
    user_repo = UserRepository(session)
    user = await user_repo.get(order.user_id)
    if not user:
        return

    lang = user.language_code or "en"
    from app.core.i18n import t

    text = t(
        "esim_ready", lang,
        iccid=esim.iccid,
        activation_code=esim.activation_code or "N/A",
        lpa=esim.lpa or "N/A",
    )

    await bot.send_message(user.telegram_id, text, parse_mode="HTML")

    # Send QR
    if esim.qr_code_data:
        import base64
        from aiogram.types import BufferedInputFile
        qr_bytes = base64.b64decode(esim.qr_code_data)
        await bot.send_photo(
            user.telegram_id,
            BufferedInputFile(qr_bytes, "esim_qr.png"),
            caption="📸 Scan to activate your eSIM",
        )
    elif esim.qr_code_url:
        await bot.send_photo(user.telegram_id, esim.qr_code_url, caption="📸 Scan to activate your eSIM")

    logger.info("user_notified_esim_ready", telegram_id=user.telegram_id, iccid=esim.iccid)


async def _notify_user_esim_failed(bot, order: Order) -> None:
    from app.repositories.repositories import UserRepository
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        user = await UserRepository(s).get(order.user_id)
    if user:
        from app.core.i18n import t
        await bot.send_message(
            user.telegram_id,
            t("payment_failed", user.language_code or "en"),
            parse_mode="HTML",
        )
