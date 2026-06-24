"""
Database Migrations
Run this file to migrate legacy schemas to the latest Phase 7 schema.
"""
import asyncio
import logging
from config.database import get_db, Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_migrations():
    logger.info("Connecting to DB...")
    db = Database.get_database()
    
    # 1. Rename product_inventory to products
    logger.info("Migrating: product_inventory -> products")
    collections = await db.list_collection_names()
    if "product_inventory" in collections:
        try:
            await db.product_inventory.rename("products", dropTarget=True)
            logger.info("✓ Renamed product_inventory to products")
        except Exception as e:
            logger.error(f"Failed to rename product_inventory: {e}")
    else:
        logger.info("- product_inventory collection not found (already migrated?)")

    # 2. Merge msg_queues data into messages (if needed) and drop msg_queues
    logger.info("Migrating: msg_queues -> messages")
    if "msg_queues" in collections:
        # Phase 4 already has messages, but let's just make sure we drop msg_queues
        # Since msg_queues is redundant and mirrors messages, dropping it is safe.
        try:
            await db.drop_collection("msg_queues")
            logger.info("✓ Dropped msg_queues collection")
        except Exception as e:
            logger.error(f"Failed to drop msg_queues: {e}")
    else:
        logger.info("- msg_queues collection not found (already dropped?)")
        
    # 3. Drop campaign_batches
    logger.info("Migrating: drop campaign_batches")
    if "campaign_batches" in collections:
        try:
            await db.drop_collection("campaign_batches")
            logger.info("✓ Dropped campaign_batches collection")
        except Exception as e:
            logger.error(f"Failed to drop campaign_batches: {e}")
    else:
        logger.info("- campaign_batches collection not found (already dropped?)")
        
    logger.info("Migration complete.")

if __name__ == "__main__":
    import dotenv
    from pathlib import Path
    dotenv.load_dotenv(Path(__file__).parent / ".env")
    asyncio.run(run_migrations())
