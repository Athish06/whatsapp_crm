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
            # ── Drop legacy indexes that conflict with the new schema ──────────
            for legacy_index in [
                "unique_customer_phone",
                "unique_customer_phone_v2",
            ]:
                try:
                    await db.customers.drop_index(legacy_index)
                except Exception:
                    pass

            # ── 1. customers collection ───────────────────────────────────────
            # Per spec: identity-only. Unique key = (shop_id, phone).
            await db.customers.create_index(
                [("shop_id", 1), ("phone", 1)],
                unique=True,
                name="unique_shop_customer_phone",
            )
            await db.customers.create_index([("user_id", 1)])
            await db.customers.create_index([("shop_id", 1)])
            await db.customers.create_index([("customer_id", 1)])

            # ── 2. files collection ───────────────────────────────────────────
            try:
                await db.files.drop_index("unique_file_upload")
            except Exception:
                pass
            await db.files.create_index(
                [("user_id", 1), ("original_file_name", 1), ("file_size", 1)],
                unique=True,
                name="unique_file_upload",
            )
            await db.files.create_index([("user_id", 1), ("data_purpose", 1)])
            await db.files.create_index([("shop_id", 1)])

            # ── 3. templates collection ───────────────────────────────────────
            await db.templates.create_index([("user_id", 1)])
            await db.templates.create_index([("segment_target", 1)])
            await db.templates.create_index([("shop_id", 1)])

            # ── 4. campaigns collection ───────────────────────────────────────
            await db.campaigns.create_index([("user_id", 1)])
            await db.campaigns.create_index([("status", 1)])
            await db.campaigns.create_index([("created_at", -1)])
            await db.campaigns.create_index([("shop_id", 1)])

            # ── 5. batches collection ─────────────────────────────────────────
            await db.batches.create_index([("user_id", 1)])
            await db.batches.create_index([("campaign_id", 1)])
            await db.batches.create_index([("status", 1)])
            await db.batches.create_index([("priority", 1)])
            await db.batches.create_index([("start_time", 1)])
            await db.batches.create_index([("shop_id", 1)])

            # ── 6. messages collection ────────────────────────────────────────
            await db.messages.create_index([("user_id", 1)])
            await db.messages.create_index([("batch_id", 1)])
            await db.messages.create_index([("customer_id", 1)])
            await db.messages.create_index([("status", 1)])
            await db.messages.create_index([("phone_number", 1)])
            await db.messages.create_index([("priority", 1)])
            await db.messages.create_index([("created_at", -1)])
            await db.messages.create_index([("shop_id", 1)])
            try:
                await db.messages.create_index(
                    [("batch_id", 1), ("customer_id", 1)],
                    unique=True,
                    name="unique_batch_customer_message",
                )
            except Exception:
                pass

            # ── 6b. msg_queues collection ─────────────────────────────────────
            await db.msg_queues.create_index([("user_id", 1)])
            await db.msg_queues.create_index([("status", 1)])
            await db.msg_queues.create_index([("priority", 1)])
            await db.msg_queues.create_index([("scheduled_at", 1)])
            await db.msg_queues.create_index([("batch_id", 1)])
            try:
                await db.msg_queues.create_index(
                    [("message_id", 1), ("user_id", 1)],
                    unique=True,
                )
            except Exception:
                pass

            # ── 7. users collection ───────────────────────────────────────────
            await db.users.create_index([("email", 1)], unique=True)

            # ── 7b. campaign_batches collection ───────────────────────────────
            await db.campaign_batches.create_index([("user_id", 1)])
            await db.campaign_batches.create_index([("campaign_id", 1)])
            await db.campaign_batches.create_index([("batch_id", 1)])
            await db.campaign_batches.create_index([("status", 1)])
            try:
                await db.campaign_batches.create_index(
                    [("campaign_id", 1), ("batch_id", 1), ("user_id", 1)],
                    unique=True,
                )
            except Exception:
                pass

            # ── 8. shops collection ───────────────────────────────────────────
            await db.shops.create_index([("user_id", 1)])
            try:
                await db.shops.create_index(
                    [("user_id", 1), ("shop_name", 1)],
                    unique=True,
                    name="unique_user_shop_name",
                )
            except Exception:
                pass

            # ── 9. product_inventory collection ──────────────────────────────
            await db.product_inventory.create_index([("shop_id", 1)])
            await db.product_inventory.create_index([("product_id", 1)])
            try:
                await db.product_inventory.create_index(
                    [("shop_id", 1), ("product_id", 1)],
                    unique=True,
                    name="unique_shop_product",
                )
            except Exception:
                pass

            # ── 10. customer_insights collection ─────────────────────────────
            # Critical: (shop_id, customer_id) → unique
            await db.customer_insights.create_index([("shop_id", 1)])
            await db.customer_insights.create_index([("customer_id", 1)])
            await db.customer_insights.create_index([("segment", 1)])
            await db.customer_insights.create_index([("updated_at", -1)])
            try:
                await db.customer_insights.create_index(
                    [("shop_id", 1), ("customer_id", 1)],
                    unique=True,
                    name="unique_shop_customer_insight",
                )
            except Exception:
                pass

            # ── 11. transactions collection ───────────────────────────────────
            # Per spec composite indexes:
            await db.transactions.create_index([("shop_id", 1), ("customer_id", 1)])
            await db.transactions.create_index([("shop_id", 1), ("purchase_date", -1)])
            await db.transactions.create_index([("shop_id", 1), ("product_id", 1)])
            await db.transactions.create_index([("shop_id", 1)])
            await db.transactions.create_index([("customer_id", 1)])
            await db.transactions.create_index([("product_id", 1)])
            await db.transactions.create_index([("purchase_date", -1)])

            logger.info("Database indexes created successfully")
        
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")


# Convenience function for dependency injection
def get_db():
    """Get database instance for FastAPI dependency injection."""
    return Database.get_database()
