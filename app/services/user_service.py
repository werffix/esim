import random
import string
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.models import User
from app.repositories.repositories import UserRepository, ReferralEarningRepository

logger = get_logger(__name__)


def generate_referral_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.referral_repo = ReferralEarningRepository(session)

    async def get_or_register(
        self,
        telegram_id: int,
        first_name: str,
        username: Optional[str],
        last_name: Optional[str],
        language_code: str = "en",
        ref_code: Optional[str] = None,
    ) -> tuple[User, bool]:
        """Get existing user or register new one. Returns (user, is_new)."""
        referrer_id: Optional[uuid.UUID] = None
        if ref_code:
            referrer = await self.user_repo.get_by_referral_code(ref_code)
            if referrer and referrer.telegram_id != telegram_id:
                referrer_id = referrer.id

        # Generate unique referral code
        while True:
            code = generate_referral_code()
            existing = await self.user_repo.get_by_referral_code(code)
            if not existing:
                break

        user, is_new = await self.user_repo.get_or_create(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            last_name=last_name,
            language_code=language_code,
            referral_code=code,
            referred_by_id=referrer_id,
        )

        if not is_new:
            # Update profile fields that may change
            user.first_name = first_name
            user.username = username
            user.last_name = last_name
            await self.session.flush()

        await self.session.commit()
        if is_new:
            logger.info("user_registered", telegram_id=telegram_id, referrer_id=str(referrer_id) if referrer_id else None)
        return user, is_new

    async def get_profile(self, telegram_id: int) -> Optional[User]:
        return await self.user_repo.get_by_telegram_id(telegram_id)

    async def get_referral_stats(self, user_id: uuid.UUID) -> dict:
        referrals = await self.user_repo.get_referrals(user_id)
        total_earned = await self.referral_repo.get_total_earned(user_id)
        return {
            "referral_count": len(referrals),
            "total_earned": total_earned,
        }

    async def ban_user(self, telegram_id: int) -> bool:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return False
        user.is_banned = True
        await self.session.commit()
        return True

    async def unban_user(self, telegram_id: int) -> bool:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return False
        user.is_banned = False
        await self.session.commit()
        return True
