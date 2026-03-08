"""
Message queue scheduler service for processing scheduled messages.
Implements the 60-second heartbeat to send WhatsApp messages with throttling and retry logic.
"""
import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class MessageQueueScheduler:
    """
    Scheduler service for processing message queue.
    Runs every 60 seconds to fetch and send pending messages.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.batch_size = 50  # Max messages to process per cycle
        self.throttle_delay = 1.5  # Seconds between messages
        self.max_retry_count = 3
    
    async def fetch_pending_messages(self) -> List[Dict[str, Any]]:
        """
        Fetch pending messages that are due for sending.
        Query: status == 'pending' AND scheduled_at <= Current_Time_UTC
        Sorted by: priority (ASC), scheduled_at (ASC)
        Limit: 50 messages per cycle
        """
        current_time = datetime.now(timezone.utc)
        
        # Find pending messages that are due
        cursor = self.db.messages.find({
            "status": "pending",
            "scheduled_at": {"$lte": current_time}
        }).sort([
            ("priority", 1),      # VIP (1) first, Regular (4) last
            ("scheduled_at", 1)   # Older messages first
        ]).limit(self.batch_size)
        
        messages = await cursor.to_list(length=self.batch_size)
        
        logger.info(f"Fetched {len(messages)} pending messages for processing")
        return messages
    
    async def mark_messages_processing(self, message_ids: List[str]) -> int:
        """
        Mark messages as 'processing' to prevent duplicate processing by other workers.
        This is the "Fetch and Lock" mechanism for concurrency safety.
        """
        result = await self.db.messages.update_many(
            {"id": {"$in": message_ids}},
            {"$set": {"status": "processing"}}
        )
        
        logger.info(f"Marked {result.modified_count} messages as processing")
        return result.modified_count
    
    async def send_whatsapp_message(self, phone_number: str, message_content: str) -> Dict[str, Any]:
        """
        Send a WhatsApp message via WhatsApp Business API.
        
        TODO: Integrate with actual WhatsApp Business API
        For now, this is a mock implementation.
        
        Args:
            phone_number: Recipient's phone number
            message_content: Message text to send
            
        Returns:
            Dict with 'success' boolean and optional 'error' message
        """
        try:
            # TODO: Replace with actual WhatsApp API call
            # Example:
            # response = await whatsapp_api.send_message(
            #     to=phone_number,
            #     body=message_content
            # )
            
            # Mock successful send for now
            logger.info(f"[MOCK] Sending message to {phone_number}: {message_content[:50]}...")
            await asyncio.sleep(0.1)  # Simulate API call
            
            return {"success": True}
        
        except Exception as e:
            logger.error(f"Error sending message to {phone_number}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a single message: send via WhatsApp and update status.
        
        Returns:
            True if successful, False if failed
        """
        message_id = message["id"]
        phone_number = message["phone_number"]
        message_content = message["message_content"]
        
        # Send the message
        result = await self.send_whatsapp_message(phone_number, message_content)
        
        if result["success"]:
            # Mark as sent
            await self.db.messages.update_one(
                {"id": message_id},
                {
                    "$set": {
                        "status": "sent",
                        "processed_at": datetime.now(timezone.utc)
                    }
                }
            )
            logger.info(f"✓ Message sent successfully to {phone_number}")
            return True
        else:
            # Handle failure with retry logic
            await self.handle_message_failure(message, result.get("error", "Unknown error"))
            return False
    
    async def handle_message_failure(self, message: Dict[str, Any], error: str):
        """
        Handle message sending failure with retry mechanism.
        
        Retry Logic:
        - Increment retry_count
        - If retry_count < 3: Reset to 'pending', boost priority to 1 (VIP)
        - If retry_count >= 3: Mark as 'failed_permanently'
        """
        message_id = message["id"]
        current_retry_count = message.get("retry_count", 0)
        new_retry_count = current_retry_count + 1
        
        # Get existing error log
        error_log = message.get("error_log", [])
        error_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "retry_count": new_retry_count
        })
        
        if new_retry_count >= self.max_retry_count:
            # Too many retries - mark as permanently failed
            await self.db.messages.update_one(
                {"id": message_id},
                {
                    "$set": {
                        "status": "failed_permanently",
                        "retry_count": new_retry_count,
                        "error_log": error_log,
                        "processed_at": datetime.now(timezone.utc)
                    }
                }
            )
            logger.warning(f"✗ Message {message_id} marked as failed_permanently after {new_retry_count} retries")
        else:
            # Retry - reset to pending with priority boost
            await self.db.messages.update_one(
                {"id": message_id},
                {
                    "$set": {
                        "status": "pending",
                        "priority": 1,  # Boost to highest priority (VIP)
                        "retry_count": new_retry_count,
                        "error_log": error_log
                    }
                }
            )
            logger.warning(f"⟳ Message {message_id} reset to pending with priority boost (retry {new_retry_count}/{self.max_retry_count})")
    
    async def process_message_queue(self):
        """
        Main worker function that runs every 60 seconds.
        This is the "heartbeat" of the scheduling system.
        
        Steps:
        1. Fetch pending messages
        2. Mark as processing (lock)
        3. Send with throttling (1.5s delay between messages)
        4. Handle success/failure with retry logic
        """
        if self.is_running:
            logger.warning("Previous cycle still running, skipping this cycle")
            return
        
        self.is_running = True
        cycle_start = datetime.now(timezone.utc)
        
        try:
            logger.info("=" * 60)
            logger.info(f"MESSAGE QUEUE HEARTBEAT - {cycle_start.isoformat()}")
            logger.info("=" * 60)
            
            # Step 1: Fetch pending messages
            messages = await self.fetch_pending_messages()
            
            if not messages:
                logger.info("No pending messages to process")
                return
            
            # Step 2: Mark as processing (fetch and lock)
            message_ids = [msg["id"] for msg in messages]
            await self.mark_messages_processing(message_ids)
            
            # Step 3 & 4: Process each message with throttling
            success_count = 0
            failure_count = 0
            
            for i, message in enumerate(messages):
                logger.info(f"Processing message {i+1}/{len(messages)} - Priority {message.get('priority', 4)}")
                
                # Send the message
                success = await self.process_message(message)
                
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                # Throttle: Wait 1.5 seconds between messages (except last one)
                if i < len(messages) - 1:
                    logger.debug(f"Throttling: waiting {self.throttle_delay}s before next message...")
                    await asyncio.sleep(self.throttle_delay)
            
            # Summary
            cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            logger.info("-" * 60)
            logger.info(f"Cycle complete: {success_count} sent, {failure_count} failed")
            logger.info(f"Duration: {cycle_duration:.2f}s")
            logger.info("=" * 60)
        
        except Exception as e:
            logger.error(f"Error in message queue processing: {str(e)}", exc_info=True)
        
        finally:
            self.is_running = False
    
    def start(self):
        """
        Start the scheduler to run every 60 seconds.
        """
        if self.scheduler.running:
            logger.warning("Scheduler already running")
            return
        
        # Add job to run every 60 seconds
        self.scheduler.add_job(
            self.process_message_queue,
            trigger=IntervalTrigger(seconds=60),
            id="message_queue_worker",
            name="Message Queue Worker",
            max_instances=1,  # Only one instance at a time
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("✓ Message queue scheduler started (60-second heartbeat)")
    
    def stop(self):
        """
        Stop the scheduler gracefully.
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("✓ Message queue scheduler stopped")
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the message queue.
        """
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        stats_cursor = self.db.messages.aggregate(pipeline)
        stats_list = await stats_cursor.to_list(length=None)
        
        stats = {item["_id"]: item["count"] for item in stats_list}
        
        return {
            "pending": stats.get("pending", 0),
            "processing": stats.get("processing", 0),
            "sent": stats.get("sent", 0),
            "failed_permanently": stats.get("failed_permanently", 0),
            "total": sum(stats.values())
        }
