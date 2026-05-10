import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import get_logger

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def refresh_esim_statuses() -> None:
    """Periodically refresh active eSIM statuses from Nova API."""
    try:
        from app.db.database import AsyncSessionLocal
        from app.esim.nova_client import get_nova_client
        from app.repositories.repositories import EsimRepository
        from app.services.esim_service import EsimService

        async with AsyncSessionLocal() as session:
            esim_repo = EsimRepository(session)
            esims = await esim_repo.get_active_for_status_update(limit=50)

            if not esims:
                return

            nova = await get_nova_client()
            esim_service = EsimService(session, nova)

            for esim in esims:
                try:
                    await esim_service.refresh_esim_status(esim)
                except Exception as exc:
                    logger.warning("esim_refresh_error", iccid=esim.iccid, error=str(exc))

            logger.debug("esim_status_refresh_done", count=len(esims))
    except Exception as exc:
        logger.error("scheduler_esim_refresh_failed", error=str(exc), exc_info=True)


async def sync_catalog_periodically() -> None:
    """Sync Nova catalog every hour."""
    try:
        from app.core.cache import get_cache
        from app.db.database import AsyncSessionLocal
        from app.esim.nova_client import get_nova_client
        from app.services.esim_service import CatalogService

        async with AsyncSessionLocal() as session:
            nova = await get_nova_client()
            cache = await get_cache()
            catalog = CatalogService(session, nova, cache)
            countries, plans = await catalog.sync_catalog()
            logger.info("scheduled_catalog_sync", countries=countries, plans=plans)
    except Exception as exc:
        logger.error("scheduled_catalog_sync_failed", error=str(exc), exc_info=True)


async def start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")

    _scheduler.add_job(
        refresh_esim_statuses,
        trigger=IntervalTrigger(minutes=5),
        id="refresh_esims",
        replace_existing=True,
    )

    _scheduler.add_job(
        sync_catalog_periodically,
        trigger=IntervalTrigger(hours=1),
        id="sync_catalog",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("scheduler_started")


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
