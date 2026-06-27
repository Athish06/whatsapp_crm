"""
Monitoring service for campaign, batch, and message drill-down.
Provides advanced analytics, error categorization, and rescheduling logic.
"""
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from config.database import get_db

class MonitoringService:
    def __init__(self, db: Any):
        self.db = db

    async def get_campaign_overview(self, shop_id: str, user_id: str) -> List[Dict[str, Any]]:
        """All campaigns for a shop with aggregated stats from the campaigns collection."""
        # The campaigns collection already maintains live aggregated stats
        # thanks to Phase 4 updates in scheduler_service.py.
        cursor = self.db.campaigns.find(
            {"shop_id": shop_id, "user_id": user_id},
            {"_id": 1, "campaign_name": 1, "status": 1, "created_at": 1, 
             "completed_at": 1, "updated_at": 1,
             "total_batches": 1, "completed_batches": 1,
             "total_customers": 1, "messages_sent": 1, "messages_failed": 1,
             "segment_stats": 1, "period_tag": 1}
        ).sort("created_at", -1)
        
        campaigns = await cursor.to_list(100)
        for c in campaigns:
            c["id"] = str(c.pop("_id"))
            if isinstance(c.get("created_at"), datetime):
                dt = c["created_at"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                c["created_at"] = dt.isoformat()
            if isinstance(c.get("completed_at"), datetime):
                dt = c["completed_at"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                c["completed_at"] = dt.isoformat()
            if isinstance(c.get("updated_at"), datetime):
                dt = c["updated_at"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                c["updated_at"] = dt.isoformat()
        return campaigns

    async def get_campaign_detail(self, campaign_id: str, user_id: str) -> Dict[str, Any]:
        """Single campaign with per-batch breakdown and aggregated message stats."""
        # Get campaign
        from bson import ObjectId
        campaign = await self.db.campaigns.find_one(
            {"_id": campaign_id, "user_id": user_id}
        )
        if not campaign:
            return None
        campaign["id"] = str(campaign.pop("_id"))
        if isinstance(campaign.get("created_at"), datetime):
            dt = campaign["created_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            campaign["created_at"] = dt.isoformat()
        if isinstance(campaign.get("completed_at"), datetime):
            dt = campaign["completed_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            campaign["completed_at"] = dt.isoformat()
        if isinstance(campaign.get("updated_at"), datetime):
            dt = campaign["updated_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            campaign["updated_at"] = dt.isoformat()

        # Get batches
        batches = await self.db.batches.find(
            {"campaign_id": campaign_id, "user_id": user_id},
            {"_id": 0}
        ).sort("batch_number", 1).to_list(1000)

        # Get high-level messages stats
        total_messages = await self.db.messages.count_documents({"campaign_id": campaign_id})
        status_counts = await self.db.messages.aggregate([
            {"$match": {"campaign_id": campaign_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]).to_list(None)
        
        counts = {item["_id"]: item["count"] for item in status_counts}

        return {
            "campaign": campaign,
            "batches": batches,
            "stats": {
                "total": total_messages,
                "sent": counts.get("sent", 0) + counts.get("delivered", 0),
                "failed": counts.get("failed", 0) + counts.get("failed_final", 0) + counts.get("failed_permanently", 0),
                "pending": counts.get("pending", 0) + counts.get("processing", 0) + counts.get("retry_wait", 0),
                "cancelled": counts.get("cancelled", 0),
            }
        }

    async def get_batch_detail(self, batch_id: str, user_id: str) -> Dict[str, Any]:
        """All messages in a batch with status + error details."""
        batch = await self.db.batches.find_one(
            {"id": batch_id, "user_id": user_id},
            {"_id": 0}
        )
        if not batch:
            return None

        messages = await self.db.messages.find(
            {"batch_id": batch_id, "user_id": user_id},
            {"_id": 0, "id": 1, "customer_name": 1, "phone_number": 1, "customer_segment": 1, 
             "status": 1, "failure_reason": 1, "error_log": 1, "priority": 1, "updated_at": 1, "message_content": 1}
        ).sort("updated_at", -1).to_list(5000)

        return {
            "batch": batch,
            "messages": messages
        }

    async def get_failed_messages(self, campaign_id: str, user_id: str) -> Dict[str, Any]:
        """All failed messages with categorized failure reasons."""
        failed_statuses = ["failed", "failed_final", "failed_permanently"]
        messages = await self.db.messages.find(
            {"campaign_id": campaign_id, "user_id": user_id, "status": {"$in": failed_statuses}},
            {"_id": 0, "id": 1, "customer_name": 1, "phone_number": 1, "status": 1, "failure_reason": 1}
        ).to_list(10000)

        # Categorize
        reasons = {
            "rate_limit": 0,
            "network": 0,
            "invalid_number": 0,
            "unknown": 0
        }
        
        for msg in messages:
            reason = msg.get("failure_reason", "")
            if reason == "rate_limit":
                reasons["rate_limit"] += 1
            elif reason == "invalid_number":
                reasons["invalid_number"] += 1
            elif "network" in str(reason).lower() or "timeout" in str(reason).lower():
                reasons["network"] += 1
            else:
                reasons["unknown"] += 1

        return {
            "total_failed": len(messages),
            "reasons_breakdown": reasons,
            "messages": messages
        }

    async def reschedule_failed(self, campaign_id: str, user_id: str, mode: str = "failed") -> Dict[str, Any]:
        """
        Reschedule failed messages.
        mode: "failed" | "all_pending" | "specific_batch"
        """
        query = {"campaign_id": campaign_id, "user_id": user_id}
        
        if mode == "failed":
            query["status"] = {"$in": ["failed", "failed_final"]}
        elif mode == "all_pending":
            query["status"] = {"$in": ["failed", "failed_final", "pending", "retry_wait", "cancelled"]}
        
        messages = await self.db.messages.find(query, {"_id": 0, "id": 1, "failure_reason": 1}).to_list(None)
        
        rescheduled = 0
        skipped = 0
        reasons_skipped = {}

        now = datetime.now(timezone.utc)
        from services.whatsapp_sender import _next_day_9am_ist_utc

        for msg in messages:
            reason = msg.get("failure_reason", "")
            
            # Smart rescheduling logic
            if reason == "invalid_number":
                skipped += 1
                reasons_skipped["invalid_number"] = reasons_skipped.get("invalid_number", 0) + 1
                continue
                
            next_attempt_at = now
            if reason == "rate_limit":
                next_attempt_at = _next_day_9am_ist_utc()
            elif "network" in str(reason).lower() or "timeout" in str(reason).lower():
                next_attempt_at = now + timedelta(minutes=5)
                
            await self.db.messages.update_one(
                {"id": msg["id"]},
                {"$set": {
                    "status": "pending",
                    "next_attempt_at": next_attempt_at,
                    "retry_count": 0,
                    "error": None,
                    "failure_reason": None,
                    "updated_at": now.isoformat()
                }}
            )
            rescheduled += 1

        return {
            "rescheduled": rescheduled,
            "skipped": skipped,
            "reasons_skipped": reasons_skipped
        }

    async def get_period_summary(self, shop_id: str, period_tag: str) -> Dict[str, Any]:
        """Stats for a specific upload period (e.g. 2026-06)."""
        # Aggregate from campaigns collection for the given period_tag
        campaigns = await self.db.campaigns.find(
            {"shop_id": shop_id, "period_tag": period_tag},
            {"_id": 0}
        ).to_list(None)
        
        total_campaigns = len(campaigns)
        total_customers_targeted = sum(c.get("total_customers", 0) for c in campaigns)
        total_sent = sum(c.get("messages_sent", 0) for c in campaigns)
        total_failed = sum(c.get("messages_failed", 0) for c in campaigns)
        
        return {
            "period_tag": period_tag,
            "total_campaigns": total_campaigns,
            "total_customers_targeted": total_customers_targeted,
            "total_sent": total_sent,
            "total_failed": total_failed,
            "campaigns": campaigns
        }
