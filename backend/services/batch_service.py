"""
Batch service for managing message batches and campaigns.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid
import math
import asyncio
import random
from schemas import BatchStatus, MessageStatus
from utils.classifier import prepare_message


class BatchService:
    """Service for batch campaign operations."""
    
    def __init__(self, db: Any):
        self.db = db

    async def _sync_campaign_batch_from_batch(self, batch_id: str, user_id: str) -> None:
        """Keep campaign_batches as live status tracker for each campaign batch."""
        batch = await self.db.batches.find_one({"id": batch_id, "user_id": user_id}, {"_id": 0})
        if not batch or not batch.get("campaign_id"):
            return

        await self.db.campaign_batches.update_one(
            {"campaign_id": batch["campaign_id"], "batch_id": batch_id, "user_id": user_id},
            {
                "$set": {
                    "campaign_name": batch.get("campaign_name"),
                    "file_id": batch.get("file_id"),
                    "batch_number": batch.get("batch_number"),
                    "total_batches": batch.get("total_batches"),
                    "status": batch.get("status"),
                    "priority": batch.get("priority", 0),
                    "customer_count": batch.get("customer_count", 0),
                    "pending_count": batch.get("pending_count", 0),
                    "success_count": batch.get("success_count", 0),
                    "failed_count": batch.get("failed_count", 0),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "campaign_id": batch["campaign_id"],
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            },
            upsert=True,
        )

    async def _enqueue_messages(self, messages: List[Dict[str, Any]], batch: Dict[str, Any]) -> None:
        """Mirror pending messages into msg_queues waiting-room collection."""
        if not messages:
            return

        queue_docs: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for msg in messages:
            queue_docs.append(
                {
                    "id": msg["id"],
                    "message_id": msg["id"],
                    "user_id": msg["user_id"],
                    "campaign_id": batch.get("campaign_id"),
                    "batch_id": msg["batch_id"],
                    "customer_id": msg["customer_id"],
                    "phone_number": msg["phone_number"],
                    "customer_segment": msg.get("customer_segment", "boring"),
                    "status": "pending",
                    "priority": msg.get("priority", 4),
                    "scheduled_at": msg.get("scheduled_at"),
                    "created_at": now,
                    "updated_at": now,
                }
            )

        await self.db.msg_queues.insert_many(queue_docs)

    
    @staticmethod
    def estimate_batch_split(
        total_customers: int,
        batch_size: int,
        cooldown_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Estimate batch splitting metrics with smart-delay math."""
        total_batches = math.ceil(total_customers / batch_size)
        # Each batch takes ~(batch_size * 1.5s send) + cooldown between batches
        batch_send_seconds = batch_size * 1.5
        total_seconds = (batch_send_seconds * total_batches) + (cooldown_seconds * (total_batches - 1))
        estimated_completion_minutes = round(total_seconds / 60, 1)

        return {
            "total_customers": total_customers,
            "batch_size": batch_size,
            "total_batches": total_batches,
            "cooldown_seconds": cooldown_seconds,
            "estimated_completion_minutes": estimated_completion_minutes,
        }
    
    async def create_batch(
        self,
        customer_ids: List[str],
        batch_size: int,
        start_time: datetime,
        priority: int,
        user_id: str,
        template_id: str = None,
        segment_templates: Dict[str, str] = None,
        campaign_name: str = None,
        file_id: str = None,
        shop_id: str = None,
        ai_mode: bool = False,
        fixed_product: str = None,
    ) -> Dict[str, Any]:
        """Create batch campaign with messages.
        
        Supports two modes:
        1. Single template (template_id): All customers get the same template
        2. Segment-based (segment_templates): Different templates for different segments
        
        AI mode: If ai_mode=True, looks up customer_behavior_map for each customer
        to fill {{offer_product_1}} with their favorite item.
        If fixed_product is set, uses that for {{fixed_product}} in all messages.
        """
        # Validate at least one template approach is provided
        if not template_id and not segment_templates:
            raise ValueError("Either template_id or segment_templates must be provided")
        
        # Get customers
        customers = await self.db.customers.find(
            {"id": {"$in": customer_ids}, "user_id": user_id},
            {"_id": 0}
        ).to_list(10000)
        
        if not customers:
            raise ValueError("No customers found")
        
        # If using segment-based templates, validate all templates exist
        if segment_templates:
            template_ids = list(segment_templates.values())
            templates = await self.db.templates.find(
                {"id": {"$in": template_ids}, "user_id": user_id},
                {"_id": 0}
            ).to_list(100)
            
            if len(templates) != len(set(template_ids)):
                raise ValueError("One or more templates not found")
            
            # Create a lookup map for templates
            templates_map = {t["id"]: t for t in templates}
        else:
            # Single template mode
            template = await self.db.templates.find_one(
                {"id": template_id, "user_id": user_id},
                {"_id": 0}
            )
            
            if not template:
                raise ValueError("Template not found")
            
            templates_map = {template_id: template}
        
        # Create campaign document for tracking
        campaign_id = str(uuid.uuid4()) if campaign_name or file_id else None
        if campaign_id:
            campaign_doc = {
                "_id": campaign_id,
                "campaign_name": campaign_name or f"Campaign {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
                "user_id": user_id,
                "shop_id": shop_id,
                "file_id": file_id,
                "ai_mode": ai_mode,
                "fixed_product": fixed_product,
                "status": "pending",
                "total_customers": len(customers),
                "total_batches": math.ceil(len(customers) / batch_size),
                "completed_batches": 0,
                "messages_sent": 0,
                "messages_failed": 0,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            await self.db.campaigns.insert_one(campaign_doc)

        # Load behavior maps if AI mode is on
        behavior_map = {}
        if ai_mode and shop_id:
            behavior_cursor = self.db.customer_behavior_map.find(
                {"shop_id": shop_id}, {"_id": 0}
            )
            async for bm in behavior_cursor:
                behavior_map[bm["customer_id"]] = bm
        
        # Split into batches
        total_batches = math.ceil(len(customers) / batch_size)
        created_batches = []
        
        for i in range(total_batches):
            start_idx = i * batch_size
            end_idx = start_idx + batch_size
            batch_customers = customers[start_idx:end_idx]
            
            batch_id = str(uuid.uuid4())
            batch_doc = {
                "id": batch_id,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "file_id": file_id,
                "shop_id": shop_id,
                "user_id": user_id,
                "batch_number": i + 1,
                "total_batches": total_batches,
                "customer_count": len(batch_customers),
                "batch_size": batch_size,
                "start_time": start_time.isoformat(),
                "status": BatchStatus.PENDING.value,
                "success_count": 0,
                "failed_count": 0,
                "pending_count": len(batch_customers),
                "priority": priority,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Add template info based on mode
            if segment_templates:
                batch_doc["segment_templates"] = segment_templates
                batch_doc["mode"] = "segment-based"
            else:
                batch_doc["template_id"] = template_id
                batch_doc["mode"] = "single-template"
            
            await self.db.batches.insert_one(batch_doc)
            await self._sync_campaign_batch_from_batch(batch_id, user_id)
            
            # Create message records
            messages = []
            for customer in batch_customers:
                # Determine which template to use
                if segment_templates:
                    customer_segment = customer.get("segment", "boring")
                    customer_template_id = segment_templates.get(customer_segment)
                    
                    if not customer_template_id:
                        # Fallback to boring or all-style mapping if segment not mapped
                        customer_template_id = segment_templates.get("boring") or segment_templates.get("all")
                    
                    if not customer_template_id:
                        continue  # Skip if no template for this segment
                    
                    customer_template = templates_map[customer_template_id]
                else:
                    customer_template = templates_map[template_id]
                    customer_template_id = template_id
                
                message_content = prepare_message(customer_template["content"], customer)
                
                # AI mode: inject offer_product_1 from behavior map
                if ai_mode and shop_id:
                    cust_phone = customer.get("phone", "")
                    cust_behavior = behavior_map.get(cust_phone) or behavior_map.get(customer.get("id", ""))
                    if cust_behavior and cust_behavior.get("fav_items"):
                        offer_product = cust_behavior["fav_items"][0].get("product_name", "")
                        message_content = message_content.replace("{{offer_product_1}}", offer_product)
                        message_content = message_content.replace("{{favorite_item}}", offer_product)
                    else:
                        message_content = message_content.replace("{{offer_product_1}}", fixed_product or "")
                        message_content = message_content.replace("{{favorite_item}}", fixed_product or "")
                
                # Fixed product mode
                if fixed_product:
                    message_content = message_content.replace("{{fixed_product}}", fixed_product)
                
                # Map segment to priority - Hybrid RFM+B Intelligence
                segment_priority_map = {
                    "vip": 1,                    # VIP Champions - highest priority
                    "at_risk": 1,                # At-Risk - urgent (same as VIP)
                    "potential_bulk": 2,         # Potential Bulk - increase spend
                    "loyal_frequent": 3,         # Loyal Frequent - reward habit
                    "boring": 4                  # Boring - low priority
                }
                customer_segment = customer.get("segment", "boring").lower()
                message_priority = segment_priority_map.get(customer_segment, 4)
                
                message_doc = {
                    "id": str(uuid.uuid4()),
                    "batch_id": batch_id,
                    "customer_id": customer["id"],
                    "phone_number": customer["phone"],
                    "customer_name": customer["name"],
                    "customer_segment": customer.get("segment", "boring"),
                    "template_id": customer_template_id,
                    "message_content": message_content,
                    "status": MessageStatus.PENDING.value,
                    "priority": message_priority,
                    "scheduled_at": start_time,
                    "retry_count": 0,
                    "error_log": [],
                    "processed_at": None,
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                messages.append(message_doc)
            
            if messages:
                await self.db.messages.insert_many(messages)
                await self._enqueue_messages(messages, batch_doc)
            
            # Remove MongoDB's _id field before adding to response
            batch_response = {k: v for k, v in batch_doc.items() if k != '_id'}
            created_batches.append(batch_response)
        
        return {
            "message": f"Created {total_batches} batches successfully",
            "batches": created_batches
        }

    async def list_batches(self, user_id: str) -> List[Dict[str, Any]]:
        """List all batches for a user."""
        batches = await self.db.batches.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        
        return batches
    
    async def get_batch_messages(self, batch_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a batch."""
        messages = await self.db.messages.find(
            {"batch_id": batch_id},
            {"_id": 0}
        ).to_list(10000)
        
        return messages
    
    async def reschedule_batch(self, batch_id: str, user_id: str) -> bool:
        """Reschedule a failed batch."""
        batch = await self.db.batches.find_one(
            {"id": batch_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not batch:
            raise ValueError("Batch not found")
        
        # Reset failed messages to pending
        await self.db.messages.update_many(
            {"batch_id": batch_id, "status": MessageStatus.FAILED.value},
            {"$set": {"status": MessageStatus.PENDING.value, "error": None}}
        )

        # Re-queue failed messages back into waiting-room
        failed_messages = await self.db.messages.find(
            {"batch_id": batch_id, "user_id": user_id, "status": MessageStatus.PENDING.value},
            {"_id": 0}
        ).to_list(10000)
        if failed_messages:
            for msg in failed_messages:
                await self.db.msg_queues.update_one(
                    {"message_id": msg["id"], "user_id": user_id},
                    {
                        "$set": {
                            "campaign_id": batch.get("campaign_id"),
                            "batch_id": batch_id,
                            "customer_id": msg.get("customer_id"),
                            "phone_number": msg.get("phone_number"),
                            "customer_segment": msg.get("customer_segment", "boring"),
                            "status": "pending",
                            "priority": msg.get("priority", 4),
                            "scheduled_at": msg.get("scheduled_at"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        "$setOnInsert": {
                            "id": msg.get("id"),
                            "message_id": msg.get("id"),
                            "user_id": user_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                    upsert=True,
                )
        
        # Update batch
        failed_count = batch.get("failed_count", 0)
        await self.db.batches.update_one(
            {"id": batch_id},
            {
                "$set": {
                    "status": BatchStatus.PENDING.value,
                    "priority": 1,
                    "failed_count": 0,
                    "pending_count": failed_count
                }
            }
        )
        await self._sync_campaign_batch_from_batch(batch_id, user_id)
        
        return True
    
    async def stop_campaign(self, campaign_id: str, user_id: str) -> Dict[str, Any]:
        """Emergency stop: cancel all pending/paused queue items for a campaign.
        The batch currently sending will finish naturally; all future batches are cancelled.
        """
        # Mark all pending batches as cancelled
        batch_result = await self.db.batches.update_many(
            {"campaign_id": campaign_id, "user_id": user_id,
             "status": {"$in": [BatchStatus.PENDING.value, BatchStatus.PAUSED.value]}},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        # Cancel pending queue items
        queue_result = await self.db.msg_queues.update_many(
            {"campaign_id": campaign_id, "user_id": user_id, "status": "pending"},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        # Mark pending messages as cancelled
        msg_result = await self.db.messages.update_many(
            {"user_id": user_id, "status": MessageStatus.PENDING.value,
             "batch_id": {"$in": [b["id"] async for b in self.db.batches.find(
                 {"campaign_id": campaign_id, "user_id": user_id}, {"_id": 0, "id": 1}
             )]}},
            {"$set": {"status": "cancelled"}}
        )
        await self.db.campaigns.update_one(
            {"_id": campaign_id, "user_id": user_id},
            {"$set": {"status": "stopped", "updated_at": datetime.now(timezone.utc)}}
        )
        return {
            "message": "Campaign stopped. Current batch will finish; future batches cancelled.",
            "batches_cancelled": batch_result.modified_count,
            "queue_cancelled": queue_result.modified_count,
        }

    async def process_pending_batches(self, user_id: str, cooldown_seconds: int = 30):
        """Background task: process pending batches sequentially with smart cooldown."""
        await asyncio.sleep(2)  # Let the HTTP response return first

        while True:
            # Next pending batch ordered by priority ASC then created_at ASC
            batch = await self.db.batches.find_one(
                {"user_id": user_id, "status": BatchStatus.PENDING.value},
                {"_id": 0},
                sort=[("priority", 1), ("created_at", 1)]
            )
            if not batch:
                break

            # Mark as sending
            await self.db.batches.update_one(
                {"id": batch["id"]},
                {"$set": {"status": BatchStatus.SENDING.value,
                          "started_at": datetime.now(timezone.utc).isoformat()}}
            )
            await self._sync_campaign_batch_from_batch(batch["id"], user_id)

            # Fetch pending queue items for this batch
            queue_items = await self.db.msg_queues.find(
                {"batch_id": batch["id"], "user_id": user_id, "status": "pending"},
                {"_id": 0, "message_id": 1, "priority": 1, "scheduled_at": 1}
            ).sort([("priority", 1), ("scheduled_at", 1)]).to_list(10000)

            message_ids = [q["message_id"] for q in queue_items if q.get("message_id")]

            if not message_ids:
                await self.db.batches.update_one(
                    {"id": batch["id"]},
                    {"$set": {"status": BatchStatus.COMPLETED.value,
                              "pending_count": 0,
                              "completed_at": datetime.now(timezone.utc).isoformat()}}
                )
                await self._sync_campaign_batch_from_batch(batch["id"], user_id)
                if batch.get("campaign_id"):
                    await self._update_campaign_stats(batch["campaign_id"])
                continue

            raw_messages = await self.db.messages.find(
                {"id": {"$in": message_ids}, "status": MessageStatus.PENDING.value},
                {"_id": 0}
            ).to_list(10000)
            message_map = {m["id"]: m for m in raw_messages}
            messages = [message_map[mid] for mid in message_ids if mid in message_map]

            success_count = 0
            failed_count = 0

            for message in messages:
                # Check if this batch was cancelled mid-flight
                fresh_batch = await self.db.batches.find_one(
                    {"id": batch["id"]}, {"_id": 0, "status": 1}
                )
                if fresh_batch and fresh_batch.get("status") == "cancelled":
                    break

                await self.db.msg_queues.update_one(
                    {"message_id": message["id"], "user_id": user_id},
                    {"$set": {"status": "processing",
                              "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                await asyncio.sleep(1.5)  # Simulate 1.5s per message

                if random.random() < 0.95:
                    await self.db.messages.update_one(
                        {"id": message["id"]},
                        {"$set": {"status": MessageStatus.SENT.value,
                                  "sent_at": datetime.now(timezone.utc).isoformat()}}
                    )
                    await self.db.msg_queues.delete_one(
                        {"message_id": message["id"], "user_id": user_id}
                    )
                    success_count += 1
                else:
                    await self.db.messages.update_one(
                        {"id": message["id"]},
                        {"$set": {"status": MessageStatus.FAILED.value,
                                  "error": "Network timeout"}}
                    )
                    await self.db.msg_queues.delete_one(
                        {"message_id": message["id"], "user_id": user_id}
                    )
                    failed_count += 1

            final_status = BatchStatus.COMPLETED.value if failed_count == 0 else BatchStatus.FAILED.value
            await self.db.batches.update_one(
                {"id": batch["id"]},
                {"$set": {"status": final_status,
                          "success_count": success_count,
                          "failed_count": failed_count,
                          "pending_count": 0,
                          "completed_at": datetime.now(timezone.utc).isoformat()}}
            )
            await self._sync_campaign_batch_from_batch(batch["id"], user_id)
            if batch.get("campaign_id"):
                await self._update_campaign_stats(batch["campaign_id"])

            # ── Smart Cooldown (Train Station delay) ────────────────────────
            # Check if there are more pending batches; if so, wait before next
            more = await self.db.batches.count_documents(
                {"user_id": user_id, "status": BatchStatus.PENDING.value}
            )
            if more > 0:
                await asyncio.sleep(cooldown_seconds)
    
    async def clear_all_batches(self, user_id: str) -> Dict[str, Any]:
        """Clear all batches and messages for a user."""
        # Delete all messages for this user
        messages_result = await self.db.messages.delete_many({"user_id": user_id})
        queue_result = await self.db.msg_queues.delete_many({"user_id": user_id})
        
        # Delete all batches for this user
        batches_result = await self.db.batches.delete_many({"user_id": user_id})
        
        # Delete all campaigns for this user
        campaigns_result = await self.db.campaigns.delete_many({"user_id": user_id})
        campaign_batches_result = await self.db.campaign_batches.delete_many({"user_id": user_id})
        
        return {
            "message": "All batches, campaigns and messages cleared successfully",
            "batches_deleted": batches_result.deleted_count,
            "messages_deleted": messages_result.deleted_count,
            "queue_deleted": queue_result.deleted_count,
            "campaigns_deleted": campaigns_result.deleted_count,
            "campaign_batches_deleted": campaign_batches_result.deleted_count,
        }

    async def pause_batch(self, batch_id: str, user_id: str) -> Dict[str, Any]:
        """Pause a scheduled batch and lock remaining pending messages."""
        batch = await self.db.batches.find_one({"id": batch_id, "user_id": user_id}, {"_id": 0})
        if not batch:
            raise ValueError("Batch not found")
        if batch.get("status") in [BatchStatus.COMPLETED.value]:
            raise ValueError("Completed batch cannot be paused")

        pending_update = await self.db.messages.update_many(
            {"batch_id": batch_id, "user_id": user_id, "status": MessageStatus.PENDING.value},
            {"$set": {"status": "paused"}}
        )
        await self.db.msg_queues.update_many(
            {"batch_id": batch_id, "user_id": user_id, "status": "pending"},
            {"$set": {"status": "paused", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        await self.db.batches.update_one(
            {"id": batch_id, "user_id": user_id},
            {"$set": {"status": BatchStatus.PAUSED.value}}
        )
        await self._sync_campaign_batch_from_batch(batch_id, user_id)

        return {"message": "Batch paused", "messages_paused": pending_update.modified_count}

    async def resume_batch(self, batch_id: str, user_id: str) -> Dict[str, Any]:
        """Resume a paused batch."""
        batch = await self.db.batches.find_one({"id": batch_id, "user_id": user_id}, {"_id": 0})
        if not batch:
            raise ValueError("Batch not found")
        if batch.get("status") == BatchStatus.COMPLETED.value:
            raise ValueError("Completed batch cannot be resumed")

        paused_update = await self.db.messages.update_many(
            {"batch_id": batch_id, "user_id": user_id, "status": "paused"},
            {"$set": {"status": MessageStatus.PENDING.value}}
        )
        await self.db.msg_queues.update_many(
            {"batch_id": batch_id, "user_id": user_id, "status": "paused"},
            {"$set": {"status": "pending", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        await self.db.batches.update_one(
            {"id": batch_id, "user_id": user_id},
            {"$set": {"status": BatchStatus.PENDING.value}}
        )
        await self._sync_campaign_batch_from_batch(batch_id, user_id)

        return {"message": "Batch resumed", "messages_reactivated": paused_update.modified_count}

    async def update_batch(
        self,
        batch_id: str,
        user_id: str,
        start_time: datetime = None,
        template_id: str = None,
        segment_templates: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """Edit batch schedule time and template assignment for unsent messages."""
        batch = await self.db.batches.find_one({"id": batch_id, "user_id": user_id}, {"_id": 0})
        if not batch:
            raise ValueError("Batch not found")
        if batch.get("status") in [BatchStatus.SENDING.value, BatchStatus.COMPLETED.value]:
            raise ValueError("Only non-running batches can be edited")

        updates = {}
        if start_time is not None:
            updates["start_time"] = start_time.isoformat()

        editable_statuses = [MessageStatus.PENDING.value, "paused", MessageStatus.FAILED.value]
        message_query = {"batch_id": batch_id, "user_id": user_id, "status": {"$in": editable_statuses}}

        if start_time is not None:
            await self.db.messages.update_many(message_query, {"$set": {"scheduled_at": start_time}})
            await self.db.msg_queues.update_many(
                {"batch_id": batch_id, "user_id": user_id},
                {"$set": {"scheduled_at": start_time, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )

        # Update message templates/content when requested
        if segment_templates:
            template_ids = list(set(segment_templates.values()))
            templates = await self.db.templates.find({"id": {"$in": template_ids}, "user_id": user_id}, {"_id": 0}).to_list(100)
            if len(templates) != len(template_ids):
                raise ValueError("One or more templates not found")
            template_map = {t["id"]: t for t in templates}

            updates["segment_templates"] = segment_templates
            updates["mode"] = "segment-based"

            msgs = await self.db.messages.find(message_query, {"_id": 0, "id": 1, "customer_id": 1, "customer_segment": 1}).to_list(10000)
            customer_ids = [m["customer_id"] for m in msgs if m.get("customer_id")]
            customers = await self.db.customers.find({"id": {"$in": customer_ids}, "user_id": user_id}, {"_id": 0}).to_list(10000)
            customer_map = {c["id"]: c for c in customers}

            for msg in msgs:
                customer = customer_map.get(msg.get("customer_id"))
                if not customer:
                    continue
                seg = (msg.get("customer_segment") or "boring").lower()
                selected_template_id = segment_templates.get(seg) or segment_templates.get("boring") or segment_templates.get("all")
                if not selected_template_id:
                    continue
                tpl = template_map.get(selected_template_id)
                if not tpl:
                    continue
                new_content = prepare_message(tpl["content"], customer)
                await self.db.messages.update_one(
                    {"id": msg["id"], "user_id": user_id},
                    {"$set": {"template_id": selected_template_id, "message_content": new_content}}
                )

        elif template_id:
            template = await self.db.templates.find_one({"id": template_id, "user_id": user_id}, {"_id": 0})
            if not template:
                raise ValueError("Template not found")

            updates["template_id"] = template_id
            updates["mode"] = "single-template"

            msgs = await self.db.messages.find(message_query, {"_id": 0, "id": 1, "customer_id": 1}).to_list(10000)
            customer_ids = [m["customer_id"] for m in msgs if m.get("customer_id")]
            customers = await self.db.customers.find({"id": {"$in": customer_ids}, "user_id": user_id}, {"_id": 0}).to_list(10000)
            customer_map = {c["id"]: c for c in customers}

            for msg in msgs:
                customer = customer_map.get(msg.get("customer_id"))
                if not customer:
                    continue
                new_content = prepare_message(template["content"], customer)
                await self.db.messages.update_one(
                    {"id": msg["id"], "user_id": user_id},
                    {"$set": {"template_id": template_id, "message_content": new_content}}
                )

        if updates:
            await self.db.batches.update_one({"id": batch_id, "user_id": user_id}, {"$set": updates})
            await self._sync_campaign_batch_from_batch(batch_id, user_id)

        return {"message": "Batch updated successfully", "batch_id": batch_id}

    async def delete_batch(self, batch_id: str, user_id: str) -> Dict[str, Any]:
        """Delete an extra/wrongly created batch and its messages."""
        batch = await self.db.batches.find_one({"id": batch_id, "user_id": user_id}, {"_id": 0})
        if not batch:
            raise ValueError("Batch not found")
        if batch.get("status") == BatchStatus.SENDING.value:
            raise ValueError("Cannot delete a batch while sending")

        messages_result = await self.db.messages.delete_many({"batch_id": batch_id, "user_id": user_id})
        queue_result = await self.db.msg_queues.delete_many({"batch_id": batch_id, "user_id": user_id})
        batch_result = await self.db.batches.delete_one({"id": batch_id, "user_id": user_id})
        await self.db.campaign_batches.delete_one({"batch_id": batch_id, "user_id": user_id})

        if batch.get("campaign_id"):
            remaining = await self.db.batches.count_documents({"campaign_id": batch.get("campaign_id"), "user_id": user_id})
            if remaining == 0:
                await self.db.campaigns.delete_one({"_id": batch.get("campaign_id"), "user_id": user_id})
            else:
                await self._update_campaign_stats(batch.get("campaign_id"))

        return {
            "message": "Batch deleted successfully",
            "batch_deleted": batch_result.deleted_count,
            "messages_deleted": messages_result.deleted_count,
            "queue_deleted": queue_result.deleted_count,
        }
    
    async def _update_campaign_stats(self, campaign_id: str):
        """Update campaign statistics with per-segment breakdown."""
        batches = await self.db.batches.find({"campaign_id": campaign_id}, {"_id": 0}).to_list(1000)
        if not batches:
            return

        completed_batches = sum(1 for b in batches if b["status"] in ["completed", "failed", "cancelled"])
        total_sent = sum(b.get("success_count", 0) for b in batches)
        total_failed = sum(b.get("failed_count", 0) for b in batches)
        total_customers = sum(b.get("customer_count", 0) for b in batches)

        # Per-segment aggregation from message records
        segment_pipeline = [
            {"$match": {"batch_id": {"$in": [b["id"] for b in batches]}}},
            {"$group": {
                "_id": "$customer_segment",
                "total": {"$sum": 1},
                "sent": {"$sum": {"$cond": [{"$in": ["$status", ["sent", "delivered"]]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            }}
        ]
        seg_cursor = self.db.messages.aggregate(segment_pipeline)
        segment_stats = {}
        async for doc in seg_cursor:
            seg = doc["_id"] or "boring"
            # How many batches of this segment
            seg_batches = [b for b in batches if any(
                True for _ in [0]  # placeholder — we compute below
            )]
            segment_stats[seg] = {
                "total": doc["total"],
                "sent": doc["sent"],
                "failed": doc["failed"],
                "pct": round(doc["sent"] / doc["total"] * 100, 1) if doc["total"] > 0 else 0,
            }

        all_statuses = {b["status"] for b in batches}
        if all_statuses <= {"completed", "failed", "cancelled"}:
            status = "completed"
        elif "sending" in all_statuses or "in_progress" in all_statuses:
            status = "sending"
        elif completed_batches > 0:
            status = "in_progress"
        elif "stopped" in all_statuses or "cancelled" in all_statuses:
            status = "stopped"
        else:
            status = "pending"

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
            }}
        )
