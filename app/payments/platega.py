import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any, Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class PlategaPayment(BaseModel):
    payment_id: str
    payment_url: str
    status: str
    amount: Decimal
    currency: str
    external_ref: str


class PlategaWebhookPayload(BaseModel):
    payment_id: str
    external_ref: str
    status: str  # success | failed | expired
    amount: Decimal
    currency: str
    paid_at: Optional[str] = None
    signature: str


class PlategaClient:
    """Platega payment gateway client."""

    def __init__(self):
        self.api_url = settings.PLATEGA_API_URL.rstrip("/")
        self.api_key = settings.PLATEGA_API_KEY
        self.secret_key = settings.PLATEGA_SECRET_KEY

    async def create_payment(
        self,
        amount: Decimal,
        currency: str,
        external_ref: str,
        description: str,
        customer_telegram_id: Optional[int] = None,
    ) -> PlategaPayment:
        payload = {
            "amount": str(amount),
            "currency": currency,
            "external_ref": external_ref,
            "description": description,
            "success_url": settings.PLATEGA_SUCCESS_URL,
            "fail_url": settings.PLATEGA_FAIL_URL,
            "webhook_url": f"{settings.APP_BASE_URL}{settings.PLATEGA_WEBHOOK_PATH}",
        }
        if customer_telegram_id:
            payload["customer_id"] = str(customer_telegram_id)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.api_url}/v1/payments",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code >= 400:
            try:
                err = response.json()
                msg = err.get("message") or response.text
            except Exception:
                msg = response.text
            raise ValueError(f"Platega error {response.status_code}: {msg}")

        data = response.json()
        payment_data = data.get("payment") or data

        logger.info(
            "platega_payment_created",
            external_ref=external_ref,
            payment_id=payment_data.get("id") or payment_data.get("payment_id"),
        )

        return PlategaPayment(
            payment_id=payment_data.get("id") or payment_data.get("payment_id"),
            payment_url=payment_data.get("payment_url") or payment_data.get("url"),
            status=payment_data.get("status", "pending"),
            amount=Decimal(str(payment_data.get("amount", amount))),
            currency=payment_data.get("currency", currency),
            external_ref=external_ref,
        )

    def verify_webhook_signature(self, payload: bytes, received_signature: str) -> bool:
        """Verify HMAC-SHA256 webhook signature from Platega."""
        expected = hmac.new(
            self.secret_key.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, received_signature)

    def parse_webhook(self, raw_body: bytes, signature: str) -> PlategaWebhookPayload:
        if not self.verify_webhook_signature(raw_body, signature):
            raise ValueError("Invalid webhook signature")

        data = json.loads(raw_body)
        return PlategaWebhookPayload(**data)


platega_client = PlategaClient()
