"""
Scheduler Worker — Deterministic 6-State Engine
================================================
Non-blocking event-loop polling worker that processes the messages
collection directly.  APScheduler serves only as a 7-second clock tick;
zero job state is kept in memory — MongoDB is the single source of truth.

6-State Lifecycle:
    pending → processing → sent            (success)
                        → retry_wait       (transient failure, attempt_count < 3)
                        → failed_permanently (terminal or exhausted retries)
                        → cancelled         (user-aborted campaign)

Gate Integration (DummyGateProvider):
    Uses MD5 bucket math for deterministic, reproducible delivery simulation:
        bucket = int(MD5(phone)[-6:], 16) % 100
        0–1   → invalid_number  (immediate permanent failure)
        2     → network_error   (3 retries → DLQ)
        3–12  → rate_limit on 1st attempt, success on 2nd+
        13–99 → instant success

Demo-Friendly Backoff:
    Attempt 1 failure → retry in 15 seconds
    Attempt 2 failure → retry in 30 seconds
    Attempt 3 failure → failed_permanently (DLQ)

Deadlock Prevention:
    - asyncio.wait_for(timeout=45s) hard-kills stalled processing threads
    - try...finally scans for orphaned 'processing' records and releases them
    - Orphan recovery: messages stuck in 'processing' for >60s are auto-reset

Timing Parameters:
    POLL_INTERVAL_SECONDS   = 7       (heartbeat frequency)
    MICRO_BATCH_SIZE        = 8       (messages per poll cycle)
    INTER_MSG_JITTER_MIN    = 0.5     (seconds between messages — fast for demo)
    INTER_MSG_JITTER_MAX    = 1.5     (seconds between messages — fast for demo)
    MAX_RETRY_COUNT         = 3       (max attempts before failed_permanently)
    RETRY_BACKOFF = [15, 30]          (seconds: attempt 1, attempt 2)
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

# ── IST working hours ─────────────────────────────────────────────────────────
WORKING_HOURS_START = 9   # 9 AM IST
WORKING_HOURS_END   = 19  # 7 PM IST

# ── Configurable Boundary Matrix ──────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 7
MICRO_BATCH_SIZE = 8
INTER_MSG_JITTER_MIN = 0.5    # fast for demo
INTER_MSG_JITTER_MAX = 1.5    # fast for demo
MAX_RETRY_COUNT = 3

# Demo-friendly backoff schedule (seconds per attempt number)
RETRY_BACKOFF_BY_ATTEMPT = {
    1: 15,   # First failure  → wait 15s
    2: 30,   # Second failure → wait 30s
}

# Orphan threshold: if a message stays 'processing' longer than this, recover it
ORPHAN_THRESHOLD_SECONDS = 60


class SchedulerWorker:
    """
    Background async worker — DB-driven 6-state message engine.
    APScheduler fires every 7s; all scheduling logic lives in MongoDB.
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
            f"jitter={INTER_MSG_JITTER_MIN}-{INTER_MSG_JITTER_MAX}s, "
            f"backoff=[15s,30s], gate=DummyGateProvider/MD5)"
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
        Queries MongoDB for due messages, processes them through the 6-state machine.
        """
        if self._processing:
            return  # Previous cycle still running — skip
        self._processing = True

        try:
            # ── Working Hours Gate ────────────────────────────────────────
            hour_ist = _now_ist().hour
            if not (WORKING_HOURS_START <= hour_ist < WORKING_HOURS_END):
                logger.debug(
                    f"[Worker] Outside working hours ({hour_ist}:xx IST). Disabled for testing."
                )
                # return  # TEMPORARILY DISABLED FOR TESTING

            # ── Orphan Recovery: release stale 'processing' records ───────
            await self._recover_orphans()

            current_time = datetime.now(timezone.utc)

            # ── Time-Window Fetch ─────────────────────────────────────────
            # Query: status IN ['pending','retry_wait'] AND next_attempt_at <= now
            query = {
                "status": {"$in": ["pending", "retry_wait"]},
                "next_attempt_at": {"$lte": current_time},
            }
            cursor = self.db.messages.find(
                query, {"_id": 0}
            ).sort([
                ("priority", 1),          # VIP first (priority=1)
                ("next_attempt_at", 1),   # Oldest due first
            ]).limit(MICRO_BATCH_SIZE)

            items = await cursor.to_list(length=MICRO_BATCH_SIZE)

            if not items:
                # ── Dynamic Macro Consolidation (Auto-Complete Check) ─────
                await self._auto_complete_campaigns()
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

                # ── Process the item (hard 45s timeout to break any deadlock) ──
                try:
                    await asyncio.wait_for(self._process_item(item), timeout=45.0)
                except asyncio.TimeoutError:
                    logger.error(
                        f"[Worker] ✗ TIMEOUT processing item {item.get('id')} — deadlock broken."
                    )
                except Exception as ex:
                    logger.error(
                        f"[Worker] ✗ Unhandled exception processing item {item.get('id')}: {ex}"
                    )
                processed += 1

                # ── Inter-message jitter (demo-friendly, fast) ──
                jitter = random.uniform(INTER_MSG_JITTER_MIN, INTER_MSG_JITTER_MAX)
                await asyncio.sleep(jitter)

            if processed > 0:
                logger.info(f"[Worker] Cycle complete: {processed} items processed")

        except Exception as e:
            logger.error(f"[Worker] Poll cycle error: {e}", exc_info=True)
        finally:
            self._processing = False

    # ──────────────────────────────────────────────────────────────────────
    # Orphan Recovery
    # ──────────────────────────────────────────────────────────────────────

    async def _recover_orphans(self):
        """
        Detect messages stuck in 'processing' longer than ORPHAN_THRESHOLD_SECONDS.
        These are caused by a previous server crash or hard timeout.
        Reset them to 'retry_wait' (or 'pending' if attempt_count == 0) with
        incremented attempt_count so they can be retried cleanly.
        """
        threshold = datetime.now(timezone.utc) - timedelta(seconds=ORPHAN_THRESHOLD_SECONDS)
        orphan_cursor = self.db.messages.find({
            "status": "processing",
            "updated_at": {"$lt": threshold.isoformat()}
        }, {"_id": 0, "id": 1, "attempt_count": 1})
        orphans = await orphan_cursor.to_list(length=50)
        for orphan in orphans:
            orphan_id = orphan.get("id")
            attempt_count = orphan.get("attempt_count", 0) + 1
            now_iso = datetime.now(timezone.utc).isoformat()
            if attempt_count >= MAX_RETRY_COUNT:
                await self.db.messages.update_one(
                    {"id": orphan_id},
                    {"$set": {
                        "status": "failed_permanently",
                        "failure_reason": "worker_crash_or_timeout",
                        "attempt_count": attempt_count,
                        "dlq_at": now_iso,
                        "updated_at": now_iso,
                    }}
                )
                logger.error(f"[Worker] ⚠ Orphan {orphan_id} exhausted retries → failed_permanently")
            else:
                backoff = RETRY_BACKOFF_BY_ATTEMPT.get(attempt_count, 30)
                next_retry = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                await self.db.messages.update_one(
                    {"id": orphan_id},
                    {"$set": {
                        "status": "retry_wait",
                        "failure_reason": "worker_crash_or_timeout",
                        "attempt_count": attempt_count,
                        "next_attempt_at": next_retry,
                        "updated_at": now_iso,
                    }}
                )
                logger.warning(f"[Worker] ⚠ Orphan {orphan_id} recovered → retry_wait (attempt {attempt_count})")

    # ──────────────────────────────────────────────────────────────────────
    # Process a single queue item
    # ──────────────────────────────────────────────────────────────────────

    async def _process_item(self, item: Dict[str, Any]):
        """
        Process a single messages item through the 6-state machine.
        Uses attempt_count (reads retry_count as fallback for old messages).
        """
        item_id = item.get("id")
        phone = item.get("phone_number", "")
        user_id = item.get("user_id", "")
        now = datetime.now(timezone.utc)

        # Read attempt_count (new field) — fallback to retry_count for backward compat
        current_attempt = item.get("attempt_count", item.get("retry_count", 0))
        # Increment BEFORE calling the gate (attempt 1 = first try)
        this_attempt = current_attempt + 1

        # ── Step 1: Atomic Concurrency Lock ──────────────────────────────
        lock_result = await self.db.messages.update_one(
            {"id": item_id, "status": {"$in": ["pending", "retry_wait"]}},
            {"$set": {
                "status": "processing",
                "attempt_count": this_attempt,
                "processing_started_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }},
        )
        if lock_result.modified_count == 0:
            return  # Another worker already grabbed it

        # ── Step 2: Get message content ───────────────────────────────────
        content = item.get("message_content", "")

        try:
            # ── Step 3: Call DummyGateProvider ────────────────────────────
            try:
                result = await ProviderAdapter.send_message(phone, content, attempt_count=this_attempt)
            except Exception as e:
                result = {
                    "success": False,
                    "provider_sid": None,
                    "error": str(e),
                    "outcome": "temporary",
                    "reschedule_at": None,
                }

            # ── Step 4: State Transition Triage ───────────────────────────
            if result.get("success"):
                await self._handle_success(item, result, now)
            elif result.get("outcome") == "permanent":
                await self._handle_permanent_failure(item, result, now, this_attempt)
            else:
                # Transient failure (network / rate_limit)
                await self._handle_transient_failure(item, result, now, this_attempt)

            # ── Step 5: Update batch & campaign stats ─────────────────────
            await self._update_batch_stats(item.get("batch_id"), user_id)
            campaign_id = item.get("campaign_id")
            if campaign_id:
                await self._update_campaign_stats(campaign_id)

        finally:
            # ── Step 6: Strict Deadlock Fallback ─────────────────────────
            # If the item is STILL 'processing' after everything (crash/timeout), release it.
            stuck_check = await self.db.messages.find_one(
                {"id": item_id, "status": "processing"}
            )
            if stuck_check:
                now_iso = datetime.now(timezone.utc).isoformat()
                logger.error(
                    f"[Worker] ⚠ Item {item_id} stuck in processing. Releasing to failed_permanently."
                )
                await self.db.messages.update_one(
                    {"id": item_id},
                    {"$set": {
                        "status": "failed_permanently",
                        "failure_reason": "worker_crash_or_timeout",
                        "dlq_at": now_iso,
                        "updated_at": now_iso,
                    }}
                )

    # ──────────────────────────────────────────────────────────────────────
    # Success Handler
    # ──────────────────────────────────────────────────────────────────────

    async def _handle_success(self, item: Dict, result: Dict, now: datetime):
        """Mark message as sent (success state)."""
        item_id = item.get("id")
        provider_sid = result.get("provider_sid", "")
        now_iso = now.isoformat()

        await self.db.messages.update_one(
            {"id": item_id},
            {"$set": {
                "status": "sent",
                "provider_sid": provider_sid,
                "delivered_at": now_iso,
                "failure_reason": None,
                "updated_at": now_iso,
            },
            "$push": {
                "error_log": {
                    "timestamp": now_iso,
                    "code": "success",
                    "message": f"Delivered via {provider_sid}",
                    "attempt_count": item.get("attempt_count", 1),
                }
            }},
        )
        logger.info(f"[Worker] ✓ SENT {item.get('phone_number')} (sid={provider_sid})")

    # ──────────────────────────────────────────────────────────────────────
    # Permanent Failure Handler (Terminal DLQ — no retries)
    # ──────────────────────────────────────────────────────────────────────

    async def _handle_permanent_failure(self, item: Dict, result: Dict, now: datetime, this_attempt: int):
        """
        Terminal failure (e.g. invalid_number).
        Bypass retries entirely — straight to failed_permanently.
        """
        item_id = item.get("id")
        error_msg = result.get("error", "permanent_failure")
        now_iso = now.isoformat()

        await self.db.messages.update_one(
            {"id": item_id},
            {"$set": {
                "status": "failed_permanently",
                "failure_reason": error_msg,
                "attempt_count": this_attempt,
                "dlq_at": now_iso,
                "delivered_at": None,
                "updated_at": now_iso,
            },
            "$push": {
                "error_log": {
                    "timestamp": now_iso,
                    "code": error_msg,
                    "message": f"Terminal failure: {error_msg}",
                    "attempt_count": this_attempt,
                }
            }},
        )
        logger.warning(
            f"[Worker] ✗ FAILED_PERMANENTLY {item.get('phone_number')} "
            f"reason={error_msg} (terminal, no retry)"
        )

    # ──────────────────────────────────────────────────────────────────────
    # Transient Failure Handler (retry or DLQ after 3 attempts)
    # ──────────────────────────────────────────────────────────────────────

    async def _handle_transient_failure(self, item: Dict, result: Dict, now: datetime, this_attempt: int):
        """
        Transient failure (network, rate_limit).
        If attempt_count < MAX_RETRY_COUNT → retry_wait with backoff.
        If attempt_count >= MAX_RETRY_COUNT → failed_permanently (DLQ).
        """
        item_id = item.get("id")
        error_msg = result.get("error", "unknown_error")
        now_iso = now.isoformat()

        error_entry = {
            "timestamp": now_iso,
            "code": error_msg,
            "message": f"Transient failure: {error_msg}",
            "attempt_count": this_attempt,
        }

        if this_attempt >= MAX_RETRY_COUNT:
            # ── Exhausted Retries → DLQ ───────────────────────────────────
            await self.db.messages.update_one(
                {"id": item_id},
                {"$set": {
                    "status": "failed_permanently",
                    "failure_reason": error_msg,
                    "attempt_count": this_attempt,
                    "dlq_at": now_iso,
                    "delivered_at": None,
                    "updated_at": now_iso,
                },
                "$push": {"error_log": error_entry}},
            )
            logger.warning(
                f"[Worker] ✗ FAILED_PERMANENTLY {item.get('phone_number')} "
                f"after {this_attempt} attempts: {error_msg}"
            )
        else:
            # ── Schedule Retry ────────────────────────────────────────────
            backoff_seconds = RETRY_BACKOFF_BY_ATTEMPT.get(this_attempt, 30)
            next_attempt_at = now + timedelta(seconds=backoff_seconds)

            await self.db.messages.update_one(
                {"id": item_id},
                {"$set": {
                    "status": "retry_wait",
                    "failure_reason": error_msg,
                    "attempt_count": this_attempt,
                    "next_attempt_at": next_attempt_at,
                    "updated_at": now_iso,
                },
                "$push": {"error_log": error_entry}},
            )
            logger.warning(
                f"[Worker] ⟳ RETRY_WAIT {item.get('phone_number')} "
                f"(attempt {this_attempt}/{MAX_RETRY_COUNT}, "
                f"next in {backoff_seconds}s at {next_attempt_at.isoformat()})"
            )

            # If rate_limit — bulk-reschedule all other pending messages for this campaign
            if error_msg == "rate_limit" and item.get("campaign_id"):
                await self.db.messages.update_many(
                    {
                        "campaign_id": item["campaign_id"],
                        "status": {"$in": ["pending", "retry_wait", "processing"]},
                        "id": {"$ne": item_id},
                    },
                    {"$set": {
                        "next_attempt_at": next_attempt_at,
                        "failure_reason": "rate_limit",
                        "status": "retry_wait",
                        "updated_at": now_iso,
                    }},
                )
                logger.warning(
                    f"[Worker] ⏰ Rate limit bulk-reschedule for campaign {item['campaign_id']}"
                )

    # ──────────────────────────────────────────────────────────────────────
    # Cancel Handler
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
    # Auto-Complete Check (Dynamic Macro Consolidation)
    # ──────────────────────────────────────────────────────────────────────

    async def _auto_complete_campaigns(self):
        """
        When the queue is empty, scan for campaigns still marked 'sending'.
        For each, count remaining active messages. If 0, flip status to 'completed'.
        This stops the frontend from showing an infinite loading spinner.

        Remaining Count Formula:
            count(messages where status IN ['pending', 'processing', 'retry_wait'])
            If count == 0 → campaign.status = 'completed'
        """
        active_campaigns = await self.db.campaigns.find(
            {"status": "sending"}, {"_id": 1}
        ).to_list(None)

        for camp in active_campaigns:
            camp_id = camp["_id"]
            remaining = await self.db.messages.count_documents({
                "campaign_id": camp_id,
                "status": {"$in": ["pending", "processing", "retry_wait"]}
            })
            if remaining == 0:
                now = datetime.now(timezone.utc)
                await self.db.campaigns.update_one(
                    {"_id": camp_id, "status": "sending"},  # Conditional: only if still 'sending'
                    {"$set": {
                        "status": "completed",
                        "completed_at": now,
                        "updated_at": now,
                    }}
                )
                logger.info(f"[Worker] 🏁 Auto-Complete: Campaign {camp_id} → completed!")

    # ──────────────────────────────────────────────────────────────────────
    # Stats Updaters
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

        # Support both 'sent' (new) and 'delivered' (legacy)
        success_count = counts.get("sent", 0) + counts.get("delivered", 0)
        failed_count = counts.get("failed_permanently", 0) + counts.get("failed_final", 0)
        pending_count = counts.get("pending", 0) + counts.get("retry_wait", 0)
        processing_count = counts.get("processing", 0)
        cancelled_count = counts.get("cancelled", 0)
        total = sum(counts.values())

        # Determine batch status
        if pending_count == 0 and processing_count == 0:
            if failed_count > 0 and success_count == 0:
                batch_status = "failed"
            else:
                batch_status = "completed"
        elif cancelled_count == total:
            batch_status = "cancelled"
        else:
            batch_status = "sending"

        update_doc = {
            "success_count": success_count,
            "failed_count": failed_count,
            "pending_count": pending_count + processing_count,
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

        # Per-segment aggregation from messages
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

        update_fields = {
            "status": status,
            "completed_batches": completed_batches,
            "total_batches": len(batches),
            "total_customers": total_customers,
            "messages_sent": total_sent,
            "messages_failed": total_failed,
            "segment_stats": segment_stats,
            "updated_at": datetime.now(timezone.utc),
        }
        if status == "completed":
            current_comp = await self.db.campaigns.find_one(
                {"_id": campaign_id}, {"_id": 0, "completed_at": 1}
            )
            if not current_comp or not current_comp.get("completed_at"):
                update_fields["completed_at"] = datetime.now(timezone.utc)

        await self.db.campaigns.update_one(
            {"_id": campaign_id},
            {"$set": update_fields},
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
            "sent": stats.get("sent", 0) + stats.get("delivered", 0),   # unified
            "failed_permanently": stats.get("failed_permanently", 0) + stats.get("failed_final", 0),
            "cancelled": stats.get("cancelled", 0),
            "total": sum(stats.values()),
        }
