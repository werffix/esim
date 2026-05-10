import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.admin.handlers import router as admin_router
from app.api.routers.webhook import router as webhook_router
from app.api.routers.tma_router import router as tma_router
from app.bot.handlers.handlers import router as main_router
from app.bot.middlewares.middlewares import (
    AntiFloodMiddleware,
    DbSessionMiddleware,
    LoggingMiddleware,
    UserMiddleware,
)
from app.core.cache import get_cache, get_redis, close_redis
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.esim.nova_client import close_nova_client, get_nova_client
from app.db.database import create_tables
from app.scheduler import start_scheduler, stop_scheduler

setup_logging()
logger = get_logger(__name__)


async def setup_bot() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    redis = await get_redis()
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    # Middlewares (order matters)
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AntiFloodMiddleware(await get_cache()))
    dp.update.middleware(UserMiddleware())

    # Routers
    dp.include_router(admin_router)
    dp.include_router(main_router)

    return bot, dp


_bot: Bot | None = None
_dp: Dispatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global _bot, _dp

    logger.info("app_startup")

    # Create tables if not exist
    await create_tables()

    # Init bot
    _bot, _dp = await setup_bot()

    # Set webhook
    webhook_url = f"{settings.APP_BASE_URL}{settings.BOT_WEBHOOK_PATH}"
    await _bot.set_webhook(
        url=webhook_url,
        secret_token=settings.BOT_WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    logger.info("webhook_set", url=webhook_url)

    # Set bot commands & menu button
    await _bot.set_my_commands([
        BotCommand(command="start", description="Home"),
        BotCommand(command="shop", description="Open eSIM Store"),
    ])
    await _bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="🛍️ Open Store",
            web_app=WebAppInfo(url="https://app.q1esim.site/tma"),
        )
    )

    # Pre-warm Nova client
    await get_nova_client()

    # Start background scheduler
    await start_scheduler()

    app.state.bot = _bot
    app.state.dp = _dp

    yield

    # Cleanup
    await stop_scheduler()
    logger.info("scheduler_stopped")

    await _bot.delete_webhook()
    await _bot.session.close()
    await close_nova_client()
    await close_redis()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Q1 eSIM Bot",
        version="1.0.0",
        docs_url=None if settings.APP_ENV == "production" else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST", "GET"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(webhook_router)
    app.include_router(tma_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "env": settings.APP_ENV}

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
