"""
Database configuration and connection management for MongoDB.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Any
import os
import logging

logger = logging.getLogger(__name__)


class Database:
    """MongoDB connection manager with singleton pattern."""
    
    client: Optional[Any] = None
    
    @classmethod
    def get_client(cls) -> Any:
        """Get the MongoDB client instance."""
        if cls.client is None:
            mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
            cls.client = AsyncIOMotorClient(mongo_url)
        return cls.client
    
    @classmethod
    def get_database(cls):
        """Get the database instance."""
        db_name = os.environ.get('DB_NAME', 'whatsapp_crm')
        return cls.get_client()[db_name]
    
    @classmethod
    async def close(cls):
        """Close the MongoDB connection."""
        if cls.client is not None:
            cls.client.close()
            cls.client = None
    
    @classmethod
    async def initialize_indexes(cls):
        """Create database indexes for performance and uniqueness."""
        db = cls.get_database()
        
        try:
            # Drop legacy unique indexes before creating campaign-scoped variants.
            try:
                await db.customers.drop_index("unique_customer_phone")
            except Exception:
                pass

            # 1. customers collection - ensure unique phone per user
            await db.customers.create_index(
                [("user_id", 1), ("campaign_id", 1), ("phone", 1)],
                unique=True,
                name="unique_customer_phone"
            )
            await db.customers.create_index([("user_id", 1), ("campaign_id", 1), ("segment", 1)])
            await db.customers.create_index([("segment", 1)])
            await db.customers.create_index([("priority", 1)])
            await db.customers.create_index([("rfm_score", -1)])
            
            # 2. files collection - prevent duplicate file uploads
            await db.files.create_index(
                [("user_id", 1), ("original_file_name", 1), ("file_size", 1)],
                unique=True,
                name="unique_file_upload"
            )
            await db.files.create_index([("user_id", 1), ("data_purpose", 1), ("linked_customer_file_id", 1)])
            await db.files.create_index([("user_id", 1), ("campaign_id", 1), ("data_purpose", 1)])
            
            # 3. templates collection
            await db.templates.create_index([("user_id", 1)])
            await db.templates.create_index([("segment_target", 1)])
            
            # 4. campaigns collection
            await db.campaigns.create_index([("user_id", 1)])
            await db.campaigns.create_index([("status", 1)])
            await db.campaigns.create_index([("created_at", -1)])
            await db.campaigns.create_index([("file_id", 1)])
            
            # 5. batches collection
            await db.batches.create_index([("user_id", 1)])
            await db.batches.create_index([("campaign_id", 1)])
            await db.batches.create_index([("status", 1)])
            await db.batches.create_index([("priority", 1)])
            await db.batches.create_index([("start_time", 1)])
            
            # 6. messages collection (message queue)
            await db.messages.create_index([("user_id", 1)])
            await db.messages.create_index([("batch_id", 1)])
            await db.messages.create_index([("customer_id", 1)])
            await db.messages.create_index([("status", 1)])
            await db.messages.create_index([("phone_number", 1)])
            await db.messages.create_index([("priority", 1)])
            await db.messages.create_index([("created_at", -1)])
            await db.messages.create_index(
                [("batch_id", 1), ("customer_id", 1)],
                unique=True,
                name="unique_batch_customer_message"
            )

            # 6b. msg_queues collection (waiting-room queue)
            await db.msg_queues.create_index([("user_id", 1)])
            await db.msg_queues.create_index([("status", 1)])
            await db.msg_queues.create_index([("priority", 1)])
            await db.msg_queues.create_index([("scheduled_at", 1)])
            await db.msg_queues.create_index([("batch_id", 1)])
            await db.msg_queues.create_index([("message_id", 1), ("user_id", 1)], unique=True)
            
            # 7. users collection
            await db.users.create_index([("email", 1)], unique=True)

            # 7b. campaign_batches collection (live delivery map)
            await db.campaign_batches.create_index([("user_id", 1)])
            await db.campaign_batches.create_index([("campaign_id", 1)])
            await db.campaign_batches.create_index([("batch_id", 1)])
            await db.campaign_batches.create_index([("status", 1)])
            await db.campaign_batches.create_index([("priority", 1)])
            await db.campaign_batches.create_index([("campaign_id", 1), ("batch_id", 1), ("user_id", 1)], unique=True)

            logger.info("Database indexes created successfully")
        
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")


# Convenience function for dependency injection
def get_db():
    """Get database instance for FastAPI dependency injection."""
    return Database.get_database()
