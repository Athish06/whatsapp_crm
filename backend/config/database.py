"""
Database configuration and connection management for MongoDB.

Phase 1 Schema Refinement (12 → 8 collections):
  - Removed: msg_queues, campaign_batches (merged into messages / campaigns)
  - Added: offers (new collection)
  - files: content-hash dedup unique index (SHA-256 on file bytes)
  - transactions: period_tag index; NO composite unique (Bug #3 fix — period-scoped replace is correct)
  - customer_insights: previous_segment, segment_changed tracking indexes
  - messages: campaign_id direct ref, offer_id, failure_reason, next_attempt_at indexes
  - product_inventory → products (alias handled via migration in server.py)
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
        """
        Create / refresh database indexes for all 8 refined collections.

        Collections (Phase 1 refined schema):
          1. users
          2. shops        — added upload_cycle field (indexed)
          3. files        — content-hash dedup unique index
          4. customers    — identity-only, unique on (shop_id, phone)
          5. products     — replaces product_inventory
          6. transactions — period_tag indexed; NO composite unique (period-scoped replace handles dedup)
          7. customer_insights — previous_segment, segment_changed tracking
          8. templates
          9. campaigns    — absorbs campaign_batches
         10. batches
         11. messages     — absorbs msg_queues; adds campaign_id, offer_id, failure_reason
         12. offers       — NEW
        """
        db = cls.get_database()
        
        try:
            # ── Drop ALL legacy indexes that conflict with the new schema ─────────
            legacy_drops = [
                # customers
                ("customers", "unique_customer_phone"),
                ("customers", "unique_customer_phone_v2"),
                # files — old shape without content_hash
                ("files", "unique_file_upload"),
                ("files", "unique_shop_file_upload"),
            ]
            for coll_name, idx_name in legacy_drops:
                try:
                    await db[coll_name].drop_index(idx_name)
                    logger.info(f"Dropped legacy index {coll_name}.{idx_name}")
                except Exception:
                    pass  # index didn't exist — that's fine

            # ══════════════════════════════════════════════════════════════════════
            # 1. users
            # ══════════════════════════════════════════════════════════════════════
            await db.users.create_index([("email", 1)], unique=True)

            # ══════════════════════════════════════════════════════════════════════
            # 2. shops  — upload_cycle for period-tagging awareness
            # ══════════════════════════════════════════════════════════════════════
            await db.shops.create_index([("user_id", 1)])
            await db.shops.create_index([("upload_cycle", 1)])
            try:
                await db.shops.create_index(
                    [("user_id", 1), ("shop_name", 1)],
                    unique=True,
                    name="unique_user_shop_name",
                )
            except Exception:
                pass

            # ══════════════════════════════════════════════════════════════════════
            # 3. files  — content-hash dedup (SHA-256)
            #
            # Unique constraint: (user_id, shop_id, data_purpose, content_hash)
            # → same file bytes for same shop+purpose → duplicate detected, skip B2 upload
            # → same file bytes for DIFFERENT shop → allowed (Bug #7 fix: still returns
            #   file_id so owner can re-process with corrected column mapping)
            # ══════════════════════════════════════════════════════════════════════
            try:
                await db.files.create_index(
                    [
                        ("user_id", 1),
                        ("shop_id", 1),
                        ("data_purpose", 1),
                        ("content_hash", 1),
                    ],
                    unique=True,
                    name="unique_file_content_hash",
                    sparse=True,  # sparse: docs without content_hash not affected
                )
            except Exception:
                pass
            await db.files.create_index([("user_id", 1), ("data_purpose", 1)])
            await db.files.create_index([("shop_id", 1)])
            await db.files.create_index([("period_tag", 1)])
            await db.files.create_index([("uploaded_at", -1)])

            # ══════════════════════════════════════════════════════════════════════
            # 4. customers  — identity-only, unique on (shop_id, phone)
            # ══════════════════════════════════════════════════════════════════════
            try:
                await db.customers.create_index(
                    [("shop_id", 1), ("phone", 1)],
                    unique=True,
                    name="unique_shop_customer_phone",
                )
            except Exception:
                pass
            await db.customers.create_index([("user_id", 1)])
            await db.customers.create_index([("shop_id", 1)])
            await db.customers.create_index([("customer_id", 1)])
            await db.customers.create_index([("period_tag", 1)])

            # ══════════════════════════════════════════════════════════════════════
            # 5. products  (renamed from product_inventory)
            #    Full-replace on upload → snapshot semantics → keep unique constraint
            # ══════════════════════════════════════════════════════════════════════
            try:
                await db.products.create_index(
                    [("shop_id", 1), ("product_id", 1)],
                    unique=True,
                    name="unique_shop_product",
                )
            except Exception:
                pass
            await db.products.create_index([("shop_id", 1)])
            await db.products.create_index([("product_id", 1)])
            await db.products.create_index([("category", 1)])

            # ── Mirror indexes on product_inventory (legacy alias — still exists in DB)
            try:
                await db.product_inventory.create_index(
                    [("shop_id", 1), ("product_id", 1)],
                    unique=True,
                    name="unique_shop_product",
                )
            except Exception:
                pass
            await db.product_inventory.create_index([("shop_id", 1)])
            await db.product_inventory.create_index([("product_id", 1)])

            # ══════════════════════════════════════════════════════════════════════
            # 6. transactions
            #
            # Unique compound index to prevent duplicate rows within the same period (Addendum A).
            # ══════════════════════════════════════════════════════════════════════
            try:
                await db.transactions.create_index(
                    [
                        ("shop_id", 1), 
                        ("customer_id", 1), 
                        ("product_id", 1), 
                        ("purchase_date", 1), 
                        ("purchase_qty", 1), 
                        ("total_amount", 1)
                    ],
                    unique=True,
                    name="unique_transaction_row"
                )
            except Exception:
                pass
            await db.transactions.create_index([("shop_id", 1), ("customer_id", 1)])
            await db.transactions.create_index([("shop_id", 1), ("purchase_date", -1)])
            await db.transactions.create_index([("shop_id", 1), ("product_id", 1)])
            await db.transactions.create_index([("shop_id", 1), ("period_tag", 1)])  # NEW
            await db.transactions.create_index([("shop_id", 1)])
            await db.transactions.create_index([("customer_id", 1)])
            await db.transactions.create_index([("product_id", 1)])
            await db.transactions.create_index([("purchase_date", -1)])
            await db.transactions.create_index([("period_tag", 1)])  # NEW

            # ══════════════════════════════════════════════════════════════════════
            # 7. customer_insights  — single source of truth for RFM
            #
            # Added: segment, previous_segment, segment_changed indexes
            # for fast segment-transition queries and churn detection.
            # ══════════════════════════════════════════════════════════════════════
            try:
                await db.customer_insights.create_index(
                    [("shop_id", 1), ("customer_id", 1)],
                    unique=True,
                    name="unique_shop_customer_insight",
                )
            except Exception:
                pass
            await db.customer_insights.create_index([("shop_id", 1)])
            await db.customer_insights.create_index([("customer_id", 1)])
            await db.customer_insights.create_index([("segment", 1)])
            await db.customer_insights.create_index([("previous_segment", 1)])   # NEW
            await db.customer_insights.create_index([("segment_changed", 1)])    # NEW
            await db.customer_insights.create_index([("updated_at", -1)])
            await db.customer_insights.create_index([("last_calculated_at", -1)])

            # ══════════════════════════════════════════════════════════════════════
            # 8. templates
            # ══════════════════════════════════════════════════════════════════════
            await db.templates.create_index([("user_id", 1)])
            await db.templates.create_index([("segment_target", 1)])
            await db.templates.create_index([("shop_id", 1)])

            # ══════════════════════════════════════════════════════════════════════
            # 9. campaigns  — absorbs campaign_batches; direct batch_ids list on doc
            # ══════════════════════════════════════════════════════════════════════
            await db.campaigns.create_index([("user_id", 1)])
            await db.campaigns.create_index([("shop_id", 1)])
            await db.campaigns.create_index([("status", 1)])
            await db.campaigns.create_index([("created_at", -1)])
            await db.campaigns.create_index([("period_tag", 1)])  # NEW

            # ══════════════════════════════════════════════════════════════════════
            # 10. batches
            # ══════════════════════════════════════════════════════════════════════
            await db.batches.create_index([("user_id", 1)])
            await db.batches.create_index([("campaign_id", 1)])
            await db.batches.create_index([("shop_id", 1)])
            await db.batches.create_index([("status", 1)])
            await db.batches.create_index([("priority", 1)])
            await db.batches.create_index([("start_time", 1)])

            # ══════════════════════════════════════════════════════════════════════
            # 11. messages  — absorbs msg_queues scheduling fields
            #
            # Added fields (now on messages, not msg_queues):
            #   campaign_id    — direct ref (was only on batch previously)
            #   offer_id       — which offer was included
            #   failure_reason — categorized: rate_limit | network | invalid_number | unknown
            #   next_attempt_at — scheduler uses this for retry timing
            #   shop_id        — for per-shop monitoring queries
            #
            # Removed: separate msg_queues collection entirely.
            # Scheduler polls messages directly using (status, next_attempt_at).
            # ══════════════════════════════════════════════════════════════════════
            await db.messages.create_index([("user_id", 1)])
            await db.messages.create_index([("batch_id", 1)])
            await db.messages.create_index([("campaign_id", 1)])              # NEW direct ref
            await db.messages.create_index([("shop_id", 1)])
            await db.messages.create_index([("customer_id", 1)])
            await db.messages.create_index([("status", 1)])
            await db.messages.create_index([("phone_number", 1)])
            await db.messages.create_index([("priority", 1)])
            await db.messages.create_index([("created_at", -1)])
            await db.messages.create_index([("offer_id", 1)])                 # NEW
            await db.messages.create_index([("failure_reason", 1)])           # NEW
            await db.messages.create_index([("next_attempt_at", 1)])          # NEW (from msg_queues)
            # Scheduler worker poll: status + next_attempt_at (replaces msg_queues worker_poll_query)
            await db.messages.create_index(
                [("status", 1), ("next_attempt_at", 1)],
                name="scheduler_poll_query",
            )
            # Campaign-scoped status lookups (replaces msg_queues campaign_status_lookup)
            await db.messages.create_index(
                [("shop_id", 1), ("campaign_id", 1), ("status", 1)],
                name="campaign_status_lookup",
            )
            # Unique: one message per customer per batch
            try:
                await db.messages.create_index(
                    [("batch_id", 1), ("customer_id", 1)],
                    unique=True,
                    name="unique_batch_customer_message",
                )
            except Exception:
                pass

            # ══════════════════════════════════════════════════════════════════════
            # 12. offers  — NEW collection
            #
            # Schema:
            #   id, shop_id, user_id, title, description,
            #   discount_type ("percentage" | "flat" | "bogo"),
            #   discount_value, product_ids[], category,
            #   target_segments[], valid_from, valid_until,
            #   is_active, created_at
            # ══════════════════════════════════════════════════════════════════════
            await db.offers.create_index([("shop_id", 1)])
            await db.offers.create_index([("user_id", 1)])
            await db.offers.create_index([("is_active", 1)])
            await db.offers.create_index([("valid_until", 1)])               # for expiry checks
            await db.offers.create_index([("target_segments", 1)])           # multi-key: array field
            await db.offers.create_index([("shop_id", 1), ("is_active", 1)]) # common filter combo

            logger.info("✓ Database indexes created/verified for all 8 refined collections (Phase 1)")
        
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")


# Convenience function for dependency injection
def get_db():
    """Get database instance for FastAPI dependency injection."""
    return Database.get_database()
