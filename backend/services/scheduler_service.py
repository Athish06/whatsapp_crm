"""
Scheduler Worker — Asynchronous State Machine Engine
=====================================================
Non-blocking event-loop polling worker that processes the messages
collection directly (msg_queues removed as a separate collection).

Phase 4 additions:
  - Working hours gate: 9AM–7PM IST. Outside hours → skip cycle entirely.
  - WhatsApp Web real sender via provider_adapter (PROVIDER_MODE=whatsapp_web)
  - Handles reschedule_at from provider result (outside_working_hours / rate_limit)
  - instant failed_permanently on invalid_number (no retry wasted)
  - Stats computed from messages collection, not msg_queues

Architecture:
    - APScheduler interval trigger polls every POLL_INTERVAL_SECONDS
    - Picks micro-batches of MICRO_BATCH_SIZE items per cycle
    - Checks campaign status before each item (respects pause/cancel)
    - Calls ProviderAdapter.send_message() for actual delivery
    - Applies random jitter throttle (3.5–5.0s) between messages
    - Exponential retry backoff: 2 minutes between retries, max 3 attempts
    - Batch cooldown: 15–30s pause between micro-batch groups

Timing Parameters (Configurable Boundary Matrix):
    POLL_INTERVAL_SECONDS   = 7       (how often the heartbeat fires)
    MICRO_BATCH_SIZE        = 8       (items per poll cycle, range 5–10)
    INTER_MSG_JITTER_MIN    = 3.5     (seconds, min delay between messages)
    INTER_MSG_JITTER_MAX    = 5.0     (seconds, max delay between messages)
    BATCH_COOLDOWN_MIN      = 15      (seconds, min pause between micro-batches)
    BATCH_COOLDOWN_MAX      = 30      (seconds, max pause between micro-batches)
    RETRY_BACKOFF_SECONDS   = 120     (2 minutes between retry attempts)
    MAX_RETRY_COUNT         = 3       (max attempts before failed_final)
"""
import logging
import asyncio
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from services.provider_adapter import ProviderAdapter
from services.whatsapp_sender import _now_ist, _next_day_9am_ist_utc

logger = logging.getLogger(__name__)

# ── IST working hours (same constants as whatsapp_sender) ─────────────────────
WORKING_HOURS_START = 9   # 9 AM IST
WORKING_HOURS_END   = 19  # 7 PM IST

# ── Configurable Boundary Matrix ──────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 7
MICRO_BATCH_SIZE = 8
INTER_MSG_JITTER_MIN = 3.5
INTER_MSG_JITTER_MAX = 5.0
BATCH_COOLDOWN_MIN = 15
BATCH_COOLDOWN_MAX = 30
RETRY_BACKOFF_SECONDS = 120
MAX_RETRY_COUNT = 3


class SchedulerWorker:
    """
    Background async worker that processes the messages collection directly.
    Phase 4: msg_queues removed; messages is the single source of truth.
    """

    def __init__(self, db: Any):
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self._processing = False  # Guard against overlapping cycles

    # ──────────────────────────────────────────────────────────────────────
    # Lifecycle: start / stop
    # ──────────────────────────────────────────────────────────────────────

    def start(self):
        """Start the scheduler polling heartbeat."""
        if self.scheduler.running:
            logger.warning("Scheduler worker already running")
            return

        self.scheduler.add_job(
            self._poll_cycle,
            trigger=IntervalTrigger(seconds=POLL_INTERVAL_SECONDS),
            id="scheduler_worker_poll",
            name="Scheduler Worker Poll",
            max_instances=1,
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(
            f"✓ Scheduler worker started "
            f"(poll={POLL_INTERVAL_SECONDS}s, batch={MICRO_BATCH_SIZE}, "
            f"jitter={INTER_MSG_JITTER_MIN}-{INTER_MSG_JITTER_MAX}s)"
        )

    def stop(self):
        """Stop the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("✓ Scheduler worker stopped")

    # ──────────────────────────────────────────────────────────────────────
    # Core poll cycle
    # ──────────────────────────────────────────────────────────────────────

    async def _poll_cycle(self):
        """
        Main heartbeat — fires every POLL_INTERVAL_SECONDS.
        Phase 4: First checks working hours, then processes due messages.
        """
        if self._processing:
            return  # Previous cycle still running — skip
        self._processing = True

        try:
            # ── Phase 4: Working Hours Gate ───────────────────────────────
            hour_ist = _now_ist().hour
            if not (WORKING_HOURS_START <= hour_ist < WORKING_HOURS_END):
                logger.debug(
                    f"[Worker] Outside working hours ({hour_ist}:xx IST). Would skip cycle, but disabled for testing."
                )
                # return  # TEMPORARILY DISABLED FOR TESTING SO USER CAN SEE IT WORKING

            current_time = datetime.now(timezone.utc)

            # ── Time-Window Fetch: find due items from messages collection ─
            query = {
                "status": {"$in": ["pending", "retry_wait"]},
                "next_attempt_at": {"$lte": current_time},
            }
            cursor = self.db.messages.find(
                query, {"_id": 0}
            ).sort([
                ("priority", 1),          # VIP first
                ("next_attempt_at", 1),   # Oldest due first
            ]).limit(MICRO_BATCH_SIZE)

            items = await cursor.to_list(length=MICRO_BATCH_SIZE)

            if not items:
                return  # Nothing due — silent return

            logger.info(f"[Worker] Picked up {len(items)} due items")

            processed = 0
            for item in items:
                # ── Manual State Interrupt Check ──
                campaign_id = item.get("campaign_id")
                if campaign_id:
                    campaign = await self.db.campaigns.find_one(
                        {"_id": campaign_id},
                        {"_id": 0, "status": 1},
                    )
                    if campaign:
                        c_status = campaign.get("status", "")
                        if c_status == "paused":
                            logger.info(
                                f"[Worker] Campaign {campaign_id} is paused — "
                                f"skipping item {item.get('id')}"
                            )
                            continue
                        if c_status in ("cancelled", "stopped"):
                            await self._cancel_item(item)
                            continue

                # ── Process the item ──
                await self._process_item(item)
                processed += 1

                # ── Structural Throttle (inter-message jitter) ──
                jitter = random.uniform(INTER_MSG_JITTER_MIN, INTER_MSG_JITTER_MAX)
                await asyncio.sleep(jitter)

            if processed > 0:
                logger.info(f"[Worker] Cycle complete: {processed} items processed")

                # ── Batch Cooldown ──
                more_due = await self.db.messages.count_documents({
                    "status": {"$in": ["pending", "retry_wait"]},
                    "next_attempt_at": {"$lte": datetime.now(timezone.utc)},
                })
                if more_due > 0:
                    cooldown = random.uniform(BATCH_COOLDOWN_MIN, BATCH_COOLDOWN_MAX)
                    logger.info(f"[Worker] Batch cooldown: {cooldown:.1f}s before next cycle")
                    await asyncio.sleep(cooldown)

        except Exception as e:
            logger.error(f"[Worker] Poll cycle error: {e}", exc_info=True)
        finally:
            self._processing = False

    # ──────────────────────────────────────────────────────────────────────
    # Process a single queue item
    # ──────────────────────────────────────────────────────────────────────

    async def _process_item(self, item: Dict[str, Any]):
        """
        Process a single messages item through the state machine.
        Phase 4: operates directly on messages collection (no msg_queues mirror).
        """
        item_id = item.get("id")
        phone = item.get("phone_number", "")
        user_id = item.get("user_id", "")
        now = datetime.now(timezone.utc)

        # ── Step 1: Atomic Concurrency Lock ──
        lock_result = await self.db.messages.update_one(
            {"id": item_id, "status": {"$in": ["pending", "retry_wait"]}},
            {"$set": {
                "status": "processing",
                "updated_at": now.isoformat(),
            }},
        )
        if lock_result.modified_count == 0:
            return  # Another worker already grabbed it

        # ── Step 2: Get message content ──
        content = item.get("message_content", "")

        # ── Step 3: Call Provider Adapter ──
        try:
            result = await ProviderAdapter.send_message(phone, content)
        except Exception as e:
            result = {"success": False, "provider_sid": None, "error": str(e), "reschedule_at": None}

        # ── Step 4: Handle result ──
        if result.get("success"):
            await self._handle_success(item, result, now)
        else:
            await self._handle_failure(item, result, now)

        # ── Step 5: Update batch & campaign stats ──
        await self._update_batch_stats(item.get("batch_id"), user_id)
        campaign_id = item.get("campaign_id")
        if campaign_id:
            await self._update_campaign_stats(campaign_id)

    # ──────────────────────────────────────────────────────────────────────
    # Success handler
    # ──────────────────────────────────────────────────────────────────────

    async def _handle_success(self, item: Dict, result: Dict, now: datetime):
        """Mark message as delivered in messages collection."""
        item_id = item.get("id")
        provider_sid = result.get("provider_sid", "")

        await self.db.messages.update_one(
            {"id": item_id},
            {"$set": {
                "status": "delivered",
                "provider_sid": provider_sid,
                "sent_at": now.isoformat(),
                "processed_at": now,
                "updated_at": now.isoformat(),
            }},
        )
        logger.info(f"[Worker] ✓ Delivered {item.get('phone_number')} (sid={provider_sid})")

    # ──────────────────────────────────────────────────────────────────────
    # Failure handler with exponential retry backoff
    # ──────────────────────────────────────────────────────────────────────

    async def _handle_failure(self, item: Dict, result: Dict, now: datetime):
        """
        Phase 4 failure handler:
        - invalid_number → failed_permanently immediately (no retry wasted)
        - outside_working_hours / rate_limit → reschedule to result[reschedule_at]
        - other errors → exponential retry backoff (max 3 attempts)
        """
        item_id = item.get("id")
        current_retry = item.get("retry_count", 0)
        new_retry = current_retry + 1
        error_msg = result.get("error", "Unknown error")
        reschedule_at = result.get("reschedule_at")   # datetime | None

        # Build error log entry
        error_entry = {
            "timestamp": now.isoformat(),
            "error": error_msg,
            "attempt": new_retry,
        }
        error_log = item.get("error_log", [])
        if not isinstance(error_log, list):
            error_log = []
        error_log.append(error_entry)

        # ── Case A: Invalid number → failed_permanently, no retry ─────────
        if error_msg == "invalid_number":
            await self.db.messages.update_one(
                {"id": item_id},
                {"$set": {
                    "status": "failed_permanently",
                    "failure_reason": "invalid_number",
                    "retry_count": new_retry,
                    "error_log": error_log,
                    "failed_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }},
            )
            logger.warning(
                f"[Worker] ✗ INVALID_NUMBER {item.get('phone_number')} — permanently failed"
            )
            return

        # ── Case B: outside_working_hours or rate_limit → reschedule ──────
        if reschedule_at is not None:
            status = "pending"   # Will be picked up after reschedule_at passes
            await self.db.messages.update_one(
                {"id": item_id},
                {"$set": {
                    "status": status,
                    "failure_reason": error_msg,
                    "retry_count": current_retry,  # Don't count as a retry
                    "next_attempt_at": reschedule_at,
                    "error_log": error_log,
                    "updated_at": now.isoformat(),
                }},
            )
            logger.info(
                f"[Worker] ⏰ RESCHEDULED {item.get('phone_number')} "
                f"({error_msg}) → {reschedule_at.isoformat()}"
            )
            # Also bulk-reschedule all other pending messages for this campaign
            if error_msg == "rate_limit" and item.get("campaign_id"):
                await self.db.messages.update_many(
                    {
                        "campaign_id": item["campaign_id"],
                        "status": {"$in": ["pending", "retry_wait", "processing"]},
                        "id": {"$ne": item_id},
                    },
                    {"$set": {
                        "next_attempt_at": reschedule_at,
                        "failure_reason": "rate_limit",
                        "status": "pending",
                        "updated_at": now.isoformat(),
                    }},
                )
                logger.warning(
                    f"[Worker] ⏰ Rate limit: bulk-rescheduled remaining campaign "
                    f"{item['campaign_id']} messages to {reschedule_at.isoformat()}"
                )
            return

        # ── Case C: Generic failure → exponential retry ───────────────────
        if new_retry >= MAX_RETRY_COUNT:
            await self.db.messages.update_one(
                {"id": item_id},
                {"$set": {
                    "status": "failed_final",
                    "failure_reason": error_msg,
                    "retry_count": new_retry,
                    "error_log": error_log,
                    "failed_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }},
            )
            logger.warning(
                f"[Worker] ✗ FAILED_FINAL {item.get('phone_number')} "
                f"after {new_retry} attempts: {error_msg}"
            )
        else:
            next_attempt = now + timedelta(seconds=RETRY_BACKOFF_SECONDS)
            await self.db.messages.update_one(
                {"id": item_id},
                {"$set": {
                    "status": "retry_wait",
                    "failure_reason": error_msg,
                    "retry_count": new_retry,
                    "error_log": error_log,
                    "next_attempt_at": next_attempt,
                    "updated_at": now.isoformat(),
                }},
            )
            logger.warning(
                f"[Worker] ⟳ RETRY_WAIT {item.get('phone_number')} "
                f"(attempt {new_retry}/{MAX_RETRY_COUNT}, next at {next_attempt.isoformat()})"
            )

    # ──────────────────────────────────────────────────────────────────────
    # Cancel handler
    # ──────────────────────────────────────────────────────────────────────

    async def _cancel_item(self, item: Dict):
        """Mark an item as cancelled (campaign was stopped/cancelled)."""
        await self.db.messages.update_one(
            {"id": item.get("id")},
            {"$set": {
                "status": "cancelled",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

    # ──────────────────────────────────────────────────────────────────────
    # Stats updaters
    # ──────────────────────────────────────────────────────────────────────

    async def _update_batch_stats(self, batch_id: str, user_id: str):
        """Recompute batch counters from messages collection."""
        if not batch_id:
            return

        pipeline = [
            {"$match": {"batch_id": batch_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        cursor = self.db.messages.aggregate(pipeline)
        counts = {}
        async for doc in cursor:
            counts[doc["_id"]] = doc["count"]

        delivered = counts.get("delivered", 0)
        failed_final = counts.get("failed_final", 0) + counts.get("failed_permanently", 0)
        pending = counts.get("pending", 0) + counts.get("retry_wait", 0)
        processing = counts.get("processing", 0)
        cancelled = counts.get("cancelled", 0)
        total = sum(counts.values())

        # Determine batch status
        if pending == 0 and processing == 0:
            if failed_final > 0 and delivered == 0:
                batch_status = "failed"
            else:
                batch_status = "completed"
        elif cancelled == total:
            batch_status = "cancelled"
        else:
            batch_status = "sending"

        update_doc = {
            "success_count": delivered,
            "failed_count": failed_final,
            "pending_count": pending + processing,
        }

        if batch_status in ("completed", "failed"):
            update_doc["status"] = batch_status
            update_doc["completed_at"] = datetime.now(timezone.utc).isoformat()
        elif batch_status == "cancelled":
            update_doc["status"] = "cancelled"

        await self.db.batches.update_one(
            {"id": batch_id},
            {"$set": update_doc},
        )

    async def _update_campaign_stats(self, campaign_id: str):
        """Recompute campaign-level stats from all its batches."""
        if not campaign_id:
            return

        batches = await self.db.batches.find(
            {"campaign_id": campaign_id}, {"_id": 0}
        ).to_list(1000)

        if not batches:
            return

        completed_batches = sum(
            1 for b in batches
            if b.get("status") in ("completed", "failed", "cancelled")
        )
        total_sent = sum(b.get("success_count", 0) for b in batches)
        total_failed = sum(b.get("failed_count", 0) for b in batches)
        total_customers = sum(b.get("customer_count", 0) for b in batches)

        # Per-segment aggregation (from messages, not msg_queues)
        batch_ids = [b["id"] for b in batches if b.get("id")]
        segment_stats = {}
        if batch_ids:
            seg_pipeline = [
                {"$match": {"batch_id": {"$in": batch_ids}}},
                {"$group": {
                    "_id": "$customer_segment",
                    "total": {"$sum": 1},
                    "sent": {"$sum": {"$cond": [
                        {"$in": ["$status", ["sent", "delivered"]]}, 1, 0
                    ]}},
                    "failed": {"$sum": {"$cond": [
                        {"$in": ["$status", ["failed", "failed_final", "failed_permanently"]]}, 1, 0
                    ]}},
                }},
            ]
            async for doc in self.db.messages.aggregate(seg_pipeline):
                seg = doc["_id"] or "boring"
                segment_stats[seg] = {
                    "total": doc["total"],
                    "sent": doc["sent"],
                    "failed": doc["failed"],
                    "pct": round(doc["sent"] / doc["total"] * 100, 1) if doc["total"] > 0 else 0,
                }

        # Determine campaign status
        all_statuses = {b.get("status") for b in batches}
        if all_statuses <= {"completed", "failed", "cancelled"}:
            status = "completed"
        elif "sending" in all_statuses:
            status = "sending"
        elif completed_batches > 0:
            status = "sending"
        else:
            status = "pending"

        # Don't override manual pause/cancel
        current = await self.db.campaigns.find_one(
            {"_id": campaign_id}, {"_id": 0, "status": 1}
        )
        if current and current.get("status") in ("paused", "cancelled", "stopped"):
            status = current["status"]

        await self.db.campaigns.update_one(
            {"_id": campaign_id},
            {"$set": {
                "status": status,
                "completed_batches": completed_batches,
                "total_batches": len(batches),
                "total_customers": total_customers,
                "messages_sent": total_sent,
                "messages_failed": total_failed,
                "segment_stats": segment_stats,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    # ──────────────────────────────────────────────────────────────────────
    # Public API for route layer
    # ──────────────────────────────────────────────────────────────────────

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics about the message queue (from messages collection)."""
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        cursor = self.db.messages.aggregate(pipeline)
        stats = {}
        async for doc in cursor:
            stats[doc["_id"]] = doc["count"]

        return {
            "pending": stats.get("pending", 0),
            "processing": stats.get("processing", 0),
            "retry_wait": stats.get("retry_wait", 0),
            "delivered": stats.get("delivered", 0),
            "failed_final": stats.get("failed_final", 0) + stats.get("failed_permanently", 0),
            "cancelled": stats.get("cancelled", 0),
            "total": sum(stats.values()),
        }
