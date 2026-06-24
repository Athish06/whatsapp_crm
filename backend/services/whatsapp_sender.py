"""
WhatsApp Web Sender — Phase 7 (Playwright Migration)
=====================================================
Sends messages via WhatsApp Web using Playwright.
Uses a persistent browser context so the user only needs to scan the QR code once.

Design decisions:
  - Playwright async API controls a visible/headless Chromium instance.
  - Persistent context saves login state to `./whatsapp_profile`.
  - Working hours check: 9AM–7PM IST.
  - Daily message counter: stored in-memory; reset at midnight IST.
  - Rate limit heuristic: if 5 consecutive failures occur → rate_limit.
"""
import asyncio
import logging
import random
import re
import time
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ── IST helpers ───────────────────────────────────────────────────────────────
IST_OFFSET = timedelta(hours=5, minutes=30)

def _now_ist() -> datetime:
    return datetime.now(timezone.utc) + IST_OFFSET

def _next_day_9am_ist_utc() -> datetime:
    """Return the next 9AM IST as a UTC datetime (for rescheduling)."""
    now_ist = _now_ist()
    next_day = now_ist.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return next_day - IST_OFFSET


class WhatsAppWebSender:
    WORKING_HOURS_START = 9   # 9 AM IST
    WORKING_HOURS_END   = 19  # 7 PM IST
    MAX_MESSAGES_PER_DAY = 200

    def __init__(self):
        self._max_per_day = int(os.environ.get("WHATSAPP_MAX_PER_DAY", str(self.MAX_MESSAGES_PER_DAY)))
        self._daily_count = 0
        self._daily_count_date: str = ""
        self._consecutive_failures = 0
        
        # Playwright state
        self.playwright = None
        self.browser_context = None
        self.page = None
        self._is_running = False

    async def start(self):
        """Initialize Playwright and open WhatsApp Web."""
        if self._is_running:
            return
            
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return

        logger.info("[WhatsAppSender] Starting Playwright persistent context...")
        self.playwright = await async_playwright().start()
        
        # Persistent context saves cookies/localstorage (QR code login)
        profile_dir = os.path.join(os.getcwd(), "whatsapp_profile")
        
        self.browser_context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=os.environ.get("WHATSAPP_HEADLESS", "false").lower() == "true",
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        self.page = await self.browser_context.new_page()
        
        # Navigate to WhatsApp
        logger.info("[WhatsAppSender] Navigating to WhatsApp Web. Please scan QR if needed.")
        await self.page.goto("https://web.whatsapp.com", wait_until="networkidle", timeout=60000)
        
        self._is_running = True
        logger.info("[WhatsAppSender] Ready.")

    async def stop(self):
        """Cleanly close Playwright."""
        if self.browser_context:
            await self.browser_context.close()
        if self.playwright:
            await self.playwright.stop()
        self._is_running = False
        logger.info("[WhatsAppSender] Stopped.")

    def _reset_daily_counter_if_needed(self):
        today_ist = _now_ist().strftime("%Y-%m-%d")
        if self._daily_count_date != today_ist:
            self._daily_count = 0
            self._daily_count_date = today_ist

    def is_within_working_hours(self) -> bool:
        hour_ist = _now_ist().hour
        return self.WORKING_HOURS_START <= hour_ist < self.WORKING_HOURS_END

    def _normalise_phone(self, phone: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", phone)
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        # For the wa.me URL, drop the '+' sign
        return cleaned.replace("+", "")

    async def send_message(self, phone: str, message: str) -> Dict[str, Any]:
        """Send a message using the active Playwright page."""
        # if not self.is_within_working_hours():
        #     return {
        #         "success": False, "provider_sid": None,
        #         "error": "outside_working_hours", "reschedule_at": _next_day_9am_ist_utc()
        #     }

        self._reset_daily_counter_if_needed()
        if self._daily_count >= self._max_per_day:
            return {
                "success": False, "provider_sid": None,
                "error": "rate_limit", "reschedule_at": _next_day_9am_ist_utc()
            }

        if self._consecutive_failures >= 5:
            self._consecutive_failures = 0
            return {
                "success": False, "provider_sid": None,
                "error": "rate_limit", "reschedule_at": _next_day_9am_ist_utc()
            }

        if not self._is_running or not self.page:
            return {
                "success": False, "provider_sid": None,
                "error": "playwright_not_running", "reschedule_at": None
            }

        clean_phone = self._normalise_phone(phone)
        encoded_message = __import__('urllib').parse.quote(message)
        
        try:
            # 1. Navigate to the chat
            await self.page.goto(f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_message}", wait_until="load")
            
            # 2. Wait for the send button to appear (or invalid number modal)
            try:
                # Wait for the chat text box/send button
                await self.page.wait_for_selector('button[aria-label="Send"]', timeout=20000)
            except Exception:
                # Check if it's an invalid number dialog
                invalid = await self.page.evaluate('''() => {
                    return document.body.innerText.includes('Phone number shared via url is invalid');
                }''')
                if invalid:
                    logger.warning(f"[WhatsAppSender] Invalid number {phone}")
                    self._consecutive_failures += 1
                    return {
                        "success": False, "provider_sid": None,
                        "error": "invalid_number", "reschedule_at": None
                    }
                raise Exception("Timeout waiting for send button or chat to load")

            # 3. Click send (or press Enter)
            await self.page.click('button[aria-label="Send"]')
            
            # 4. Wait for message to actually send (a simple wait for network to settle)
            await asyncio.sleep(2)
            
            self._consecutive_failures = 0
            self._daily_count += 1
            sid = f"wa_{int(time.time())}"
            logger.info(f"[WhatsAppSender] ✓ Sent to {phone} (sid={sid})")
            
            return {
                "success": True, "provider_sid": sid,
                "error": None, "reschedule_at": None
            }
            
        except Exception as exc:
            self._consecutive_failures += 1
            logger.warning(f"[WhatsAppSender] Send failed to {phone}: {exc}")
            return {
                "success": False, "provider_sid": None,
                "error": str(exc), "reschedule_at": None
            }

# ── Module-level singleton ────────────────────────────────────────────────────
_sender_instance: WhatsAppWebSender | None = None

def get_whatsapp_sender() -> WhatsAppWebSender:
    global _sender_instance
    if _sender_instance is None:
        _sender_instance = WhatsAppWebSender()
    return _sender_instance
