"""
Provider Adapter — Swappable Messaging Interface
=================================================
Implements the Adapter Design Pattern so the scheduler worker never
directly interacts with external APIs.  It calls:

    result = await ProviderAdapter.send_message(phone, content)

The adapter reads PROVIDER_MODE from .env and routes to the correct
sub-module.  All providers return a Uniform Transaction Schema:

    { "success": bool, "provider_sid": str|None, "error": str|None }
"""
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

    async def send(self, phone: str, content: str) -> Dict[str, Any]:
        raise NotImplementedError


# ─── Mock Provider (Development / Testing) ────────────────────────────────────

class MockProvider(BaseProvider):
    """
    Simulates real-world delivery with configurable success rate.
    95% success, 5% random failures with varied error messages.
    """

    FAILURE_REASONS = [
        "Network timeout — remote host unreachable",
        "Target client node has no active WhatsApp account",
        "Rate limit exceeded — retry after cooldown",
        "Bad gateway — upstream provider returned 502",
        "Connection reset by peer during TLS handshake",
    ]

    async def send(self, phone: str, content: str) -> Dict[str, Any]:
        # Simulate network latency (100-300ms)
        await asyncio.sleep(random.uniform(0.1, 0.3))

        if random.random() < 0.95:
            sid = f"mock_{uuid.uuid4().hex[:12]}"
            logger.info(f"[MockProvider] ✓ Delivered to {phone} (sid={sid})")
            return {"success": True, "provider_sid": sid, "error": None}
        else:
            error = random.choice(self.FAILURE_REASONS)
            logger.warning(f"[MockProvider] ✗ Failed to {phone}: {error}")
            return {"success": False, "provider_sid": None, "error": error}


# ─── Twilio Provider (Sandbox / Production) ───────────────────────────────────

class TwilioProvider(BaseProvider):
    """
    Twilio WhatsApp Business API adapter.
    Maps variables into the strict sandbox template format:
        "Your appointment is coming up on {{1}} at {{2}}."

    TODO: Implement with actual twilio SDK when credentials are ready.
    """

    async def send(self, phone: str, content: str) -> Dict[str, Any]:
        # Placeholder — will integrate twilio SDK
        logger.info(f"[TwilioProvider] Stub — would send to {phone}")
        return {
            "success": False,
            "provider_sid": None,
            "error": "TwilioProvider not yet implemented — set PROVIDER_MODE=mock",
        }


# ─── WhatsApp Web Automation Provider ─────────────────────────────────────────

class WhatsAppWebProvider(BaseProvider):
    """
    Unofficial WhatsApp Web automation adapter.
    Bypasses sandbox restrictions and sends raw custom text
    directly via a Python web automation client.

    TODO: Implement with your preferred web automation library.
    """

    async def send(self, phone: str, content: str) -> Dict[str, Any]:
        logger.info(f"[WhatsAppWebProvider] Stub — would send to {phone}")
        return {
            "success": False,
            "provider_sid": None,
            "error": "WhatsAppWebProvider not yet implemented — set PROVIDER_MODE=mock",
        }


# ─── Adapter Router ──────────────────────────────────────────────────────────

# Provider registry
_PROVIDERS = {
    "mock": MockProvider,
    "twilio": TwilioProvider,
    "whatsapp_web": WhatsAppWebProvider,
}

# Singleton instance cache
_provider_instance = None


class ProviderAdapter:
    """
    Static adapter router.  The scheduler calls this — never a provider directly.

    Usage:
        result = await ProviderAdapter.send_message("+91...", "Hello {{customer_name}}")
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
                    f"Valid options: {list(_PROVIDERS.keys())}. Falling back to mock."
                )
                provider_cls = MockProvider
            _provider_instance = provider_cls()
            logger.info(f"[ProviderAdapter] Initialized provider: {provider_cls.__name__}")
        return _provider_instance

    @staticmethod
    async def send_message(phone: str, content: str) -> Dict[str, Any]:
        """
        Send a message through the active provider.

        Returns:
            { "success": bool, "provider_sid": str|None, "error": str|None }
        """
        provider = ProviderAdapter._get_provider()
        try:
            return await provider.send(phone, content)
        except Exception as e:
            logger.error(f"[ProviderAdapter] Unhandled exception sending to {phone}: {e}")
            return {
                "success": False,
                "provider_sid": None,
                "error": f"Adapter exception: {str(e)}",
            }
