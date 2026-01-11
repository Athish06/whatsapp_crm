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
        template_id: str,
        customer_ids: List[str],
        batch_size: int,
        start_time: datetime,
        priority: int,
        user_id: str
    ) -> Dict[str, Any]:
        """Create batch campaign with messages."""
        # Get template
        template = await self.db.templates.find_one(
            {"id": template_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not template:
            raise ValueError("Template not found")
        
        # Get customers
        customers = await self.db.customers.find(
            {"id": {"$in": customer_ids}, "user_id": user_id},
            {"_id": 0}
        ).to_list(10000)
        
        if not customers:
            raise ValueError("No customers found")
        
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
                "user_id": user_id,
                "template_id": template_id,
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
            
            await self.db.batches.insert_one(batch_doc)
            
            # Create message records
            messages = []
            for customer in batch_customers:
                message_content = prepare_message(template["content"], customer)
                message_doc = {
                    "id": str(uuid.uuid4()),
                    "batch_id": batch_id,
                    "customer_id": customer["id"],
                    "phone_number": customer["phone"],
                    "customer_name": customer["name"],
                    "message_content": message_content,
                    "status": MessageStatus.PENDING.value,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                messages.append(message_doc)
            
            if messages:
                await self.db.messages.insert_many(messages)
            
            created_batches.append(batch_doc)
        
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
