import json
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_pool: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


class CacheManager:
    PREFIX = "q1esim:"

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    async def get(self, key: str) -> Optional[Any]:
        raw = await self.redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        serialized = json.dumps(value, default=str)
        await self.redis.setex(self._key(key), ttl, serialized)

    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    async def delete_pattern(self, pattern: str) -> None:
        keys = await self.redis.keys(self._key(pattern))
        if keys:
            await self.redis.delete(*keys)

    async def exists(self, key: str) -> bool:
        return bool(await self.redis.exists(self._key(key)))

    async def incr(self, key: str, ttl: Optional[int] = None) -> int:
        full_key = self._key(key)
        value = await self.redis.incr(full_key)
        if ttl and value == 1:
            await self.redis.expire(full_key, ttl)
        return value

    async def get_rate_limit(self, user_id: int, window: int = 60) -> int:
        key = f"rate:{user_id}"
        return await self.incr(key, ttl=window)

    # FSM storage helpers
    async def set_fsm_data(self, user_id: int, data: dict, ttl: int = 3600) -> None:
        await self.set(f"fsm:{user_id}", data, ttl=ttl)

    async def get_fsm_data(self, user_id: int) -> Optional[dict]:
        return await self.get(f"fsm:{user_id}")

    async def clear_fsm(self, user_id: int) -> None:
        await self.delete(f"fsm:{user_id}")


async def get_cache() -> CacheManager:
    redis = await get_redis()
    return CacheManager(redis)
