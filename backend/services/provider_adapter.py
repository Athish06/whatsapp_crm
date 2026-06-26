"""
Provider Adapter — Swappable Messaging Interface
=================================================
Implements the Adapter Design Pattern so the scheduler worker never
directly interacts with external APIs.  It calls:

    result = await ProviderAdapter.send_message(phone, content, attempt_count)

The adapter reads PROVIDER_MODE from .env and routes to the correct
sub-module.  All providers return a Uniform Transaction Schema:

    {
        "success": bool,
        "provider_sid": str | None,
        "error": str | None,          # "network", "rate_limit", "invalid_number", or None
        "outcome": str                 # "success" | "temporary" | "permanent"
    }
"""
import hashlib
import os
import asyncio
import random
import logging
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)


# ─── Abstract base ────────────────────────────────────────────────────────────

class BaseProvider:
    """Base class for all messaging providers."""

    async def send(self, phone: str, content: str, attempt_count: int = 1) -> Dict[str, Any]:
        raise NotImplementedError


# ─── DummyGateProvider — Deterministic MD5 Bucket Gate ───────────────────────

class DummyGateProvider(BaseProvider):
    """
    Deterministic Simulated Transport Gate.

    Uses MD5 cryptographic hashing to produce a stable, reproducible bucket
    (0–99) for every phone number.  The bucket determines the message's
    lifecycle track — every demo run produces identical distributions.

    Bucket Math:
        hash_hex = MD5(phone.encode('utf-8')).hexdigest()
        tail_int = int(hash_hex[-6:], 16)        # 0 .. 16,777,215
        bucket   = tail_int % 100                 # 0 .. 99

    Track mapping (for a 200-customer dataset):
        0–1   → Terminal DLQ Track   (4 customers) — invalid_number → failed_permanently immediately
        2     → Exhausted Network Track (1 customer) — network_error × 3 retries then DLQ
        3–12  → Automated Recovery Track (20 customers) — rate_limit on attempt 1, success on attempt 2+
        13–99 → Clean Track (175 customers) — instant success on first try
    """

    @staticmethod
    def _bucket(phone: str) -> int:
        """Compute stable MD5 bucket (0–99) for a given phone string."""
        # Normalise: strip spaces and parentheses, keep country code
        normalised = phone.strip().replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
        hash_hex = hashlib.md5(normalised.encode("utf-8")).hexdigest()
        tail_int = int(hash_hex[-6:], 16)
        return tail_int % 100

    async def send(self, phone: str, content: str, attempt_count: int = 1) -> Dict[str, Any]:
        # Simulate minimal network latency (50–150ms)
        await asyncio.sleep(random.uniform(0.05, 0.15))

        bucket = self._bucket(phone)

        # ── Track 1: Terminal DLQ (buckets 0–1) ───────────────────────────
        if bucket <= 1:
            logger.warning(f"[DummyGate] ✗ TERMINAL bucket={bucket} phone={phone} → invalid_number")
            return {
                "success": False,
                "provider_sid": None,
                "error": "invalid_number",
                "outcome": "permanent",
            }

        # ── Track 2: Exhausted Network (bucket 2) ─────────────────────────
        if bucket == 2:
            logger.warning(f"[DummyGate] ✗ NETWORK_ERROR bucket={bucket} phone={phone} attempt={attempt_count}")
            return {
                "success": False,
                "provider_sid": None,
                "error": "network_error",
                "outcome": "temporary",
            }

        # ── Track 3: Automated Recovery (buckets 3–12) ───────────────────
        if 3 <= bucket <= 12:
            if attempt_count == 1:
                # First attempt: trigger a rate_limit back-off
                logger.warning(f"[DummyGate] ✗ RATE_LIMIT bucket={bucket} phone={phone} attempt={attempt_count} → retry_wait")
                return {
                    "success": False,
                    "provider_sid": None,
                    "error": "rate_limit",
                    "outcome": "temporary",
                }
            else:
                # Second attempt onwards: success
                sid = f"sim_gate_{uuid.uuid4().hex[:8]}"
                logger.info(f"[DummyGate] ✓ RECOVERED bucket={bucket} phone={phone} attempt={attempt_count} sid={sid}")
                return {
                    "success": True,
                    "provider_sid": sid,
                    "error": None,
                    "outcome": "success",
                }

        # ── Track 4: Clean (buckets 13–99) ───────────────────────────────
        sid = f"sim_gate_{uuid.uuid4().hex[:8]}"
        logger.info(f"[DummyGate] ✓ CLEAN bucket={bucket} phone={phone} sid={sid}")
        return {
            "success": True,
            "provider_sid": sid,
            "error": None,
            "outcome": "success",
        }


# ─── Twilio Provider (Sandbox / Production) ───────────────────────────────────

class TwilioProvider(BaseProvider):
    """
    Twilio WhatsApp Business API adapter.
    Maps variables into the strict sandbox template format.
    TODO: Implement with actual twilio SDK when credentials are ready.
    """

    async def send(self, phone: str, content: str, attempt_count: int = 1) -> Dict[str, Any]:
        logger.info(f"[TwilioProvider] Stub — would send to {phone}")
        return {
            "success": False,
            "provider_sid": None,
            "error": "TwilioProvider not yet implemented — set PROVIDER_MODE=mock",
            "outcome": "permanent",
        }


# ─── WhatsApp Web Automation Provider ─────────────────────────────────────────

class WhatsAppWebProvider(BaseProvider):
    """
    Real WhatsApp Web automation provider.
    Delegates to WhatsAppWebSender (pywhatkit + pyautogui).
    PROVIDER_MODE=whatsapp_web activates this provider.
    """

    async def send(self, phone: str, content: str, attempt_count: int = 1) -> Dict[str, Any]:
        from services.whatsapp_sender import get_whatsapp_sender
        sender = get_whatsapp_sender()
        result = await sender.send_message(phone, content)
        return {
            "success": result["success"],
            "provider_sid": result.get("provider_sid"),
            "error": result.get("error"),
            "outcome": "success" if result["success"] else "temporary",
            "reschedule_at": result.get("reschedule_at"),
        }


# ─── Adapter Router ──────────────────────────────────────────────────────────

_PROVIDERS = {
    "mock": DummyGateProvider,
    "simulator": DummyGateProvider,
    "twilio": TwilioProvider,
    "whatsapp_web": WhatsAppWebProvider,
}

_provider_instance = None


class ProviderAdapter:
    """
    Static adapter router.  The scheduler calls this — never a provider directly.

    Usage:
        result = await ProviderAdapter.send_message("+91...", "Hello", attempt_count=1)
    """

    @staticmethod
    def _get_provider() -> BaseProvider:
        global _provider_instance
        if _provider_instance is None:
            mode = os.environ.get("PROVIDER_MODE", "mock").lower().strip()
            provider_cls = _PROVIDERS.get(mode)
            if provider_cls is None:
                logger.error(
                    f"Unknown PROVIDER_MODE='{mode}'. "
                    f"Valid options: {list(_PROVIDERS.keys())}. Falling back to mock (DummyGateProvider)."
                )
                provider_cls = DummyGateProvider
            _provider_instance = provider_cls()
            logger.info(f"[ProviderAdapter] Initialized provider: {provider_cls.__name__}")
        return _provider_instance

    @staticmethod
    async def send_message(phone: str, content: str, attempt_count: int = 1) -> Dict[str, Any]:
        """
        Send a message through the active provider.

        Returns:
            { "success": bool, "provider_sid": str|None, "error": str|None, "outcome": str }
        """
        provider = ProviderAdapter._get_provider()
        try:
            return await provider.send(phone, content, attempt_count)
        except Exception as e:
            logger.error(f"[ProviderAdapter] Unhandled exception sending to {phone}: {e}")
            return {
                "success": False,
                "provider_sid": None,
                "error": f"adapter_exception: {str(e)}",
                "outcome": "temporary",
            }
