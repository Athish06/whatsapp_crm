"""
Batch service for managing message batches and campaigns.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import math
import asyncio
import random
from schemas import BatchStatus, MessageStatus
from utils.classifier import prepare_message


class BatchService:
    """Service for batch campaign operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    @staticmethod
    def estimate_batch_split(
        total_customers: int, 
        batch_size: int
    ) -> Dict[str, Any]:
        """Estimate batch splitting metrics."""
        total_batches = math.ceil(total_customers / batch_size)
        split_time_seconds = total_customers * 0.01
        estimated_completion_minutes = (total_customers * 2) / 60
        
        return {
            "total_customers": total_customers,
            "batch_size": batch_size,
            "total_batches": total_batches,
            "split_time_seconds": round(split_time_seconds, 2),
            "estimated_completion_minutes": round(estimated_completion_minutes, 2)
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
        file_id: str = None
    ) -> Dict[str, Any]:
        """Create batch campaign with messages.
        
        Supports two modes:
        1. Single template (template_id): All customers get the same template
        2. Segment-based (segment_templates): Different templates for different segments
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
                "file_id": file_id,
                "status": "pending",
                "total_customers": len(customers),
                "total_batches": math.ceil(len(customers) / batch_size),
                "completed_batches": 0,
                "messages_sent": 0,
                "messages_failed": 0,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            await self.db.campaigns.insert_one(campaign_doc)
        
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
                "file_id": file_id,
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
            
            # Create message records
            messages = []
            for customer in batch_customers:
                # Determine which template to use
                if segment_templates:
                    customer_segment = customer.get("segment", "regular")
                    customer_template_id = segment_templates.get(customer_segment)
                    
                    if not customer_template_id:
                        # Fallback to regular template if segment not mapped
                        customer_template_id = segment_templates.get("regular")
                    
                    if not customer_template_id:
                        continue  # Skip if no template for this segment
                    
                    customer_template = templates_map[customer_template_id]
                else:
                    customer_template = templates_map[template_id]
                    customer_template_id = template_id
                
                message_content = prepare_message(customer_template["content"], customer)
                
                # Map segment to priority (1=VIP, 2=Loyal, 3=Potential, 4=Regular)
                segment_priority_map = {
                    "vip": 1,
                    "loyal": 2,
                    "potential": 3,
                    "regular": 4
                }
                customer_segment = customer.get("segment", "regular").lower()
                message_priority = segment_priority_map.get(customer_segment, 4)
                
                message_doc = {
                    "id": str(uuid.uuid4()),
                    "batch_id": batch_id,
                    "customer_id": customer["id"],
                    "phone_number": customer["phone"],
                    "customer_name": customer["name"],
                    "customer_segment": customer.get("segment", "regular"),
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
        
        return True
    
    async def process_pending_batches(self, user_id: str):
        """Background task to process pending batches."""
        await asyncio.sleep(2)  # Initial delay
        
        while True:
            # Get next pending batch
            batch = await self.db.batches.find_one(
                {"user_id": user_id, "status": BatchStatus.PENDING.value},
                {"_id": 0}
            )
            
            if not batch:
                break
            
            # Update batch status to sending
            await self.db.batches.update_one(
                {"id": batch["id"]},
                {"$set": {"status": BatchStatus.SENDING.value}}
            )
            
            # Get messages for this batch
            messages = await self.db.messages.find(
                {"batch_id": batch["id"], "status": MessageStatus.PENDING.value},
                {"_id": 0}
            ).to_list(10000)
            
            success_count = 0
            failed_count = 0
            
            for message in messages:
                # Simulate sending with delay
                await asyncio.sleep(1.5)
                
                # Simulate 95% success rate
                if random.random() < 0.95:
                    await self.db.messages.update_one(
                        {"id": message["id"]},
                        {
                            "$set": {
                                "status": MessageStatus.SENT.value,
                                "sent_at": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    )
                    success_count += 1
                else:
                    await self.db.messages.update_one(
                        {"id": message["id"]},
                        {
                            "$set": {
                                "status": MessageStatus.FAILED.value,
                                "error": "Network timeout"
                            }
                        }
                    )
                    failed_count += 1
            
            # Update batch status
            final_status = (
                BatchStatus.FAILED.value 
                if failed_count > 0 
                else BatchStatus.COMPLETED.value
            )
            await self.db.batches.update_one(
                {"id": batch["id"]},
                {
                    "$set": {
                        "status": final_status,
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "pending_count": 0,
                        "completed_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Update campaign stats if batch is part of a campaign
            if batch.get("campaign_id"):
                await self._update_campaign_stats(batch["campaign_id"])
    
    async def clear_all_batches(self, user_id: str) -> Dict[str, Any]:
        """Clear all batches and messages for a user."""
        # Delete all messages for this user
        messages_result = await self.db.messages.delete_many({"user_id": user_id})
        
        # Delete all batches for this user
        batches_result = await self.db.batches.delete_many({"user_id": user_id})
        
        # Delete all campaigns for this user
        campaigns_result = await self.db.campaigns.delete_many({"user_id": user_id})
        
        return {
            "message": "All batches, campaigns and messages cleared successfully",
            "batches_deleted": batches_result.deleted_count,
            "messages_deleted": messages_result.deleted_count,
            "campaigns_deleted": campaigns_result.deleted_count
        }
    
    async def _update_campaign_stats(self, campaign_id: str):
        """Update campaign statistics after batch completion."""
        # Get all batches for this campaign
        batches = await self.db.batches.find({"campaign_id": campaign_id}).to_list(1000)
        
        completed_batches = sum(1 for b in batches if b["status"] in ["completed", "failed"])
        total_sent = sum(b.get("success_count", 0) for b in batches)
        total_failed = sum(b.get("failed_count", 0) for b in batches)
        
        # Determine campaign status
        if completed_batches == len(batches):
            status = "completed"
        elif completed_batches > 0:
            status = "in_progress"
        else:
            status = "pending"
        
        # Update campaign document
        await self.db.campaigns.update_one(
            {"_id": campaign_id},
            {
                "$set": {
                    "status": status,
                    "completed_batches": completed_batches,
                    "messages_sent": total_sent,
                    "messages_failed": total_failed,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
