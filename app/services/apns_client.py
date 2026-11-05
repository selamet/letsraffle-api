"""
Minimal APNs HTTP/2 client with token based (.p8) authentication
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

PRODUCTION_HOST = "https://api.push.apple.com"
SANDBOX_HOST = "https://api.sandbox.push.apple.com"
# Apple accepts provider tokens for up to 60 minutes; refresh a bit earlier.
PROVIDER_TOKEN_TTL = 50 * 60


class DeliveryResult(str, Enum):
    SENT = "sent"
    # Token is no longer valid; the device registration should be removed.
    INVALID_TOKEN = "invalid_token"
    FAILED = "failed"


@dataclass
class APNsConfig:
    key_id: str
    team_id: str
    private_key: str
    topic: str
    use_sandbox: bool

    @classmethod
    def from_settings(cls) -> Optional["APNsConfig"]:
        key = settings.apns_key
        if not key and settings.apns_key_path:
            try:
                with open(settings.apns_key_path) as handle:
                    key = handle.read()
            except OSError as exc:
                logger.warning(f"APNs key could not be read: {exc}")
                return None
        if not (settings.apns_key_id and settings.apns_team_id and key):
            return None
        return cls(
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            private_key=key.replace("\\n", "\n"),
            topic=settings.apns_topic,
            use_sandbox=settings.apns_use_sandbox,
        )


class APNsClient:
    """Sends alert notifications to APNs. Reuses one HTTP/2 connection."""

    def __init__(self, config: APNsConfig, transport: Optional[httpx.BaseTransport] = None):
        self.config = config
        self._token: Optional[str] = None
        self._token_issued_at = 0.0
        self._client = httpx.Client(
            http2=transport is None,
            transport=transport,
            base_url=SANDBOX_HOST if config.use_sandbox else PRODUCTION_HOST,
            timeout=10,
        )

    def provider_token(self) -> str:
        now = time.time()
        if not self._token or now - self._token_issued_at > PROVIDER_TOKEN_TTL:
            self._token = jwt.encode(
                {"iss": self.config.team_id, "iat": int(now)},
                self.config.private_key,
                algorithm="ES256",
                headers={"kid": self.config.key_id},
            )
            self._token_issued_at = now
        return self._token

    def send(self, device_token: str, payload: dict) -> DeliveryResult:
        headers = {
            "authorization": f"bearer {self.provider_token()}",
            "apns-topic": self.config.topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }
        try:
            response = self._client.post(f"/3/device/{device_token}", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning(f"APNs request failed: {exc}")
            return DeliveryResult.FAILED

        if response.status_code == 200:
            return DeliveryResult.SENT

        reason = ""
        try:
            reason = response.json().get("reason", "")
        except ValueError:
            pass
        if response.status_code == 410 or reason in {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}:
            return DeliveryResult.INVALID_TOKEN

        logger.warning(f"APNs rejected notification: status={response.status_code}, reason={reason}")
        return DeliveryResult.FAILED
