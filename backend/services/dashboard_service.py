"""
Dashboard service for aggregating statistics.
"""
from typing import Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import BatchStatus, MessageStatus


class DashboardService:
    """Service for dashboard statistics."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard statistics for a user."""
        # Total customers
        total_customers = await self.db.customers.count_documents(
            {"user_id": user_id}
        )
        
        # Messages sent (successfully)
        messages_sent = await self.db.messages.count_documents(
            {"status": MessageStatus.SENT.value}
        )
        
        # Messages failed
        messages_failed = await self.db.messages.count_documents(
            {"status": MessageStatus.FAILED.value}
        )
        
        # Active batches (pending or sending)
        active_batches = await self.db.batches.count_documents({
            "user_id": user_id,
            "status": {"$in": [BatchStatus.PENDING.value, BatchStatus.SENDING.value]}
        })
        
        # Templates count
        templates_count = await self.db.templates.count_documents(
            {"user_id": user_id}
        )
        
        return {
            "total_customers": total_customers,
            "messages_sent": messages_sent,
            "messages_failed": messages_failed,
            "active_batches": active_batches,
            "templates_count": templates_count
        }
