import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Response Schemas ───────────────────────────────────────────────────────

class NovaCountry(BaseModel):
    country_code: str
    plan_count: int


class NovaPlan(BaseModel):
    id: str
    country_code: str
    name: str
    data_gb: Optional[float] = None
    is_unlimited: bool = False
    validity_days: int
    price_usd: str
    kind: str = "data"
    speed: Optional[str] = None
    ip_country: Optional[str] = None
    in_stock: bool = True


class NovaEsimCreated(BaseModel):
    iccid: str
    lpa: Optional[str] = None
    activation_code: Optional[str] = None
    qr_url: Optional[str] = None
    status: str = "inactive"


class NovaEsimDetail(BaseModel):
    iccid: str
    lpa: Optional[str] = None
    activation_code: Optional[str] = None
    qr_url: Optional[str] = None
    status: str
    data_total_mb: Optional[int] = None
    data_used_mb: Optional[int] = None
    expires_at: Optional[str] = None
    activated_at: Optional[str] = None


class NovaQRCode(BaseModel):
    iccid: str
    qr_url: Optional[str] = None
    qr_base64: Optional[str] = None
    lpa: Optional[str] = None


class NovaBalance(BaseModel):
    amount: float
    currency: str


# ─── Client ──────────────────────────────────────────────────────────────────

class NovaEsimAPIError(Exception):
    def __init__(self, status_code: int, message: str, raw: Any = None):
        self.status_code = status_code
        self.message = message
        self.raw = raw
        super().__init__(f"Nova API error {status_code}: {message}")


class NovaEsimClient:
    """Production client for Nova eSIM Reseller API with HMAC-SHA256 auth."""

    def __init__(
        self,
        base_url: str = settings.NOVA_API_BASE_URL,
        api_key: str = settings.NOVA_API_KEY,
        api_secret: str = settings.NOVA_API_SECRET,
        timeout: int = settings.NOVA_API_TIMEOUT,
        retry_count: int = settings.NOVA_API_RETRY_COUNT,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.retry_count = retry_count
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "NovaEsimClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()

    def _sign_request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
    ) -> dict[str, str]:
        """
        Build HMAC-SHA256 signature headers.

        canonical_string:
            {METHOD}\\n
            {path?query}\\n
            {timestamp}\\n
            {nonce}\\n
            {sha256(body)}
        """
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)

        body_hash = hashlib.sha256(body or b"").hexdigest()

        canonical = "\n".join([method.upper(), path, timestamp, nonce, body_hash])

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Any:
        assert self._client is not None, "Client not initialised — use async context manager"

        body_bytes = json.dumps(json_body).encode() if json_body else b""

        # Build path including query string for signing
        parsed_path = path
        if params:
            from urllib.parse import urlencode
            parsed_path = f"{path}?{urlencode(params)}"

        headers = self._sign_request(method, parsed_path, body_bytes)

        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(1, self.retry_count + 1):
            try:
                logger.debug("nova_api_request", method=method, path=path, attempt=attempt)
                response = await self._client.request(
                    method=method,
                    url=path,
                    params=params,
                    content=body_bytes if json_body else None,
                    headers=headers,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning("nova_api_rate_limit", retry_after=retry_after)
                    import asyncio
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    raise NovaEsimAPIError(response.status_code, "Server error", response.text)

                if response.status_code >= 400:
                    try:
                        data = response.json()
                        msg = data.get("message") or data.get("error") or response.text
                    except Exception:
                        msg = response.text
                    raise NovaEsimAPIError(response.status_code, msg, response.text)

                return response.json()

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning("nova_api_retry", attempt=attempt, error=str(exc))
                import asyncio
                await asyncio.sleep(2 ** (attempt - 1))

        raise last_exc

    # ─── API Methods ─────────────────────────────────────────────────────────

    async def get_countries(self) -> list[NovaCountry]:
        data = await self._request("GET", "/v1/catalog/countries")
        return [NovaCountry(**c) for c in (data.get("countries") or data)]

    async def get_plans(self, country_code: Optional[str] = None) -> list[NovaPlan]:
        params = {"country_code": country_code} if country_code else None
        data = await self._request("GET", "/v1/catalog/plans", params=params)
        return [NovaPlan(**p) for p in (data.get("plans") or data)]

    async def create_esim(self, plan_id: str, external_ref: str) -> NovaEsimCreated:
        payload = {"plan_id": plan_id, "external_ref": external_ref}
        data = await self._request("POST", "/v1/esims", json_body=payload)
        esim_data = data.get("esim") or data
        return NovaEsimCreated(**esim_data)

    async def get_esim(self, iccid: str) -> NovaEsimDetail:
        data = await self._request("GET", f"/v1/esims/{iccid}")
        esim_data = data.get("esim") or data
        return NovaEsimDetail(**esim_data)

    async def delete_esim(self, iccid: str) -> bool:
        await self._request("DELETE", f"/v1/esims/{iccid}")
        return True

    async def get_esim_qr(self, iccid: str) -> NovaQRCode:
        data = await self._request("GET", f"/v1/esims/{iccid}/qr")
        return NovaQRCode(**{**data, "iccid": iccid})

    async def get_orders(self, page: int = 1, limit: int = 50) -> list[dict]:
        data = await self._request("GET", "/v1/orders", params={"page": page, "limit": limit})
        return data.get("orders") or data

    async def get_balance(self) -> NovaBalance:
        data = await self._request("GET", "/v1/balance")
        return NovaBalance(**data)


# Singleton for dependency injection
_nova_client: Optional[NovaEsimClient] = None


async def get_nova_client() -> NovaEsimClient:
    global _nova_client
    if _nova_client is None:
        _nova_client = NovaEsimClient()
        await _nova_client.__aenter__()
    return _nova_client


async def close_nova_client() -> None:
    global _nova_client
    if _nova_client is not None:
        await _nova_client.__aexit__(None, None, None)
        _nova_client = None
