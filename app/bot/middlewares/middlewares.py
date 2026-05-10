from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from app.core.cache import CacheManager
from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import AsyncSessionLocal
from app.services.user_service import UserService

logger = get_logger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Inject async DB session into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


class UserMiddleware(BaseMiddleware):
    """Auto-register user and inject into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract user from update
        telegram_user = None
        ref_code = None

        if isinstance(event, Update):
            if event.message:
                telegram_user = event.message.from_user
                # Check /start with referral
                text = event.message.text or ""
                if text.startswith("/start "):
                    ref_code = text.split(" ", 1)[1].strip() or None
            elif event.callback_query:
                telegram_user = event.callback_query.from_user

        if telegram_user and "session" in data:
            session = data["session"]
            user_service = UserService(session)
            user, is_new = await user_service.get_or_register(
                telegram_id=telegram_user.id,
                first_name=telegram_user.first_name,
                username=telegram_user.username,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code or "en",
                ref_code=ref_code,
            )
            data["user"] = user
            data["lang"] = user.language_code or "en"
            data["is_new_user"] = is_new

            if user.is_banned:
                logger.warning("banned_user_attempt", telegram_id=telegram_user.id)
                return  # Silently ignore banned users

        return await handler(event, data)


class AntiFloodMiddleware(BaseMiddleware):
    """Rate limiting middleware using Redis."""

    def __init__(self, cache: CacheManager):
        self.cache = cache
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        message: Message | None = None

        if isinstance(event, Update):
            if event.message:
                user_id = event.message.from_user.id if event.message.from_user else None
                message = event.message
            elif event.callback_query:
                user_id = event.callback_query.from_user.id

        if user_id:
            count = await self.cache.get_rate_limit(user_id, window=settings.RATE_LIMIT_WINDOW)
            if count > settings.RATE_LIMIT_MESSAGES:
                logger.warning("rate_limit_hit", user_id=user_id, count=count)
                if message:
                    await message.answer("⚠️ Too many requests. Please slow down.")
                return

        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """Structured logging for all updates."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        event_type = type(event).__name__

        if isinstance(event, Update):
            if event.message and event.message.from_user:
                user_id = event.message.from_user.id
            elif event.callback_query and event.callback_query.from_user:
                user_id = event.callback_query.from_user.id

        logger.debug("bot_update", event_type=event_type, user_id=user_id)

        try:
            return await handler(event, data)
        except Exception as exc:
            logger.error("handler_error", event_type=event_type, user_id=user_id, error=str(exc), exc_info=True)
            raise
