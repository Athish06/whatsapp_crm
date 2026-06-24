"""
Shop service for managing shops and their data lifecycle.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import uuid
import logging

import logging
import pandas as pd

logger = logging.getLogger(__name__)


class ShopService:
    """Service for shop operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def create_shop(self, user_id: str, shop_name: str, upload_cycle: str = "monthly") -> Dict[str, Any]:
        """Create a new shop for the user."""
        shop_id = str(uuid.uuid4())
        shop_doc = {
            "id": shop_id,
            "user_id": user_id,
            "shop_name": shop_name,
            "upload_cycle": upload_cycle,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.shops.insert_one(shop_doc)
        return {k: v for k, v in shop_doc.items() if k != "_id"}

    async def list_shops(self, user_id: str) -> List[Dict[str, Any]]:
        """List all shops with CSV upload status and live campaign stats."""
        shops = await self.db.shops.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(100)

        enriched = []
        for shop in shops:
            shop_id = shop["id"]
            # CSV status: find latest file per data_purpose
            csv_status = {}
            for purpose in ["customer_data", "product_data", "transaction_data"]:
                latest_file = await self.db.files.find_one(
                    {"shop_id": shop_id, "data_purpose": purpose},
                    {"_id": 0, "uploaded_at": 1, "original_file_name": 1},
                    sort=[("uploaded_at", -1)],
                )
                csv_status[purpose] = {
                    "uploaded": latest_file is not None,
                    "last_updated": latest_file["uploaded_at"].isoformat() if latest_file and isinstance(latest_file.get("uploaded_at"), datetime) else (latest_file["uploaded_at"] if latest_file else None),
                    "file_name": latest_file["original_file_name"] if latest_file else None,
                }

            # Counts
            customer_count = await self.db.customers.count_documents(
                {"user_id": user_id, "shop_id": shop_id}
            )
            product_count = await self.db.products.count_documents(
                {"shop_id": shop_id}
            )
            transaction_count = await self.db.transactions.count_documents(
                {"shop_id": shop_id}
            )

            # Live campaign stats
            active_batches = await self.db.batches.count_documents(
                {"user_id": user_id, "shop_id": shop_id, "status": {"$in": ["pending", "scheduled", "sending"]}}
            )

            # Aggregate sent/failed/pending message counts for this shop's batches
            batch_ids_cursor = self.db.batches.find(
                {"user_id": user_id, "shop_id": shop_id},
                {"_id": 0, "id": 1}
            )
            batch_ids = [b["id"] async for b in batch_ids_cursor]

            sent_count = 0
            failed_count = 0
            pending_count = 0
            if batch_ids:
                sent_count = await self.db.messages.count_documents(
                    {"batch_id": {"$in": batch_ids}, "status": {"$in": ["sent", "delivered"]}}
                )
                failed_count = await self.db.messages.count_documents(
                    {"batch_id": {"$in": batch_ids}, "status": {"$in": ["failed", "failed_permanently"]}}
                )
                pending_count = await self.db.messages.count_documents(
                    {"batch_id": {"$in": batch_ids}, "status": {"$in": ["pending", "processing", "paused"]}}
                )

            total_campaigns = await self.db.campaigns.count_documents(
                {"user_id": user_id, "shop_id": shop_id}
            )

            shop["csv_status"] = csv_status
            shop["customer_count"] = customer_count
            shop["product_count"] = product_count
            shop["transaction_count"] = transaction_count
            shop["live_stats"] = {
                "active_batches": active_batches,
                "total_campaigns": total_campaigns,
                "sent": sent_count,
                "failed": failed_count,
                "pending": pending_count,
                "total_messages": sent_count + failed_count + pending_count,
            }
            enriched.append(shop)

        return enriched

    async def get_shop_detail(self, shop_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get full shop detail including CSV status, counts, and behavioral insights."""
        shop = await self.db.shops.find_one(
            {"id": shop_id, "user_id": user_id}, {"_id": 0}
        )
        if not shop:
            return None

        # CSV status
        csv_status = {}
        for purpose in ["customer_data", "product_data", "transaction_data"]:
            latest_file = await self.db.files.find_one(
                {"shop_id": shop_id, "data_purpose": purpose},
                {"_id": 0, "uploaded_at": 1, "original_file_name": 1},
                sort=[("uploaded_at", -1)],
            )
            csv_status[purpose] = {
                "uploaded": latest_file is not None,
                "last_updated": latest_file["uploaded_at"].isoformat() if latest_file and isinstance(latest_file.get("uploaded_at"), datetime) else (latest_file["uploaded_at"] if latest_file else None),
                "file_name": latest_file["original_file_name"] if latest_file else None,
            }

        # ── Customer segmentation (Single Source of Truth) ──
        # Join customers with customer_insights to ensure we only count targetable customers,
        # and include customers with no transactions as "boring".
        customer_pipeline = [
            {"$match": {"shop_id": shop_id}},
            {
                "$lookup": {
                    "from": "customer_insights",
                    "let": {"cust_key": {"$ifNull": ["$customer_id", "$phone"]}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$customer_id", "$$cust_key"]}}},
                        {"$match": {"shop_id": shop_id}}
                    ],
                    "as": "insight"
                }
            },
            {
                "$unwind": {
                    "path": "$insight",
                    "preserveNullAndEmptyArrays": True
                }
            },
            {
                "$project": {
                    "segment": {"$ifNull": ["$insight.segment", "boring"]}
                }
            },
            {
                "$group": {
                    "_id": "$segment",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        seg_cursor = self.db.customers.aggregate(customer_pipeline)
        segment_counts = {}
        async for doc in seg_cursor:
            segment_counts[doc["_id"] or "boring"] = doc["count"]

        # Product category breakdown
        cat_pipeline = [
            {"$match": {"shop_id": shop_id}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        ]
        cat_cursor = self.db.products.aggregate(cat_pipeline)
        category_breakdown = {}
        async for doc in cat_cursor:
            category_breakdown[doc["_id"]] = doc["count"]

        # Behavioral insights (from transactions)
        top_products_pipeline = [
            {"$match": {"shop_id": shop_id}},
            {"$group": {
                "_id": {"category": "$category", "product_id": "$product_id"},
                "total_qty": {"$sum": {"$ifNull": ["$purchase_qty", "$quantity"]}},
                "total_amount": {"$sum": {"$ifNull": ["$total_amount", "$amount"]}},
            }},
            {"$sort": {"total_qty": -1}},
        ]
        top_cursor = self.db.transactions.aggregate(top_products_pipeline)
        top_products_by_category = {}
        async for doc in top_cursor:
            cat = doc["_id"]["category"]
            if cat and cat not in top_products_by_category:
                # Get product name
                product = await self.db.products.find_one(
                    {"shop_id": shop_id, "product_id": doc["_id"]["product_id"]},
                    {"_id": 0, "product_name": 1},
                )
                top_products_by_category[cat] = {
                    "product_id": doc["_id"]["product_id"],
                    "product_name": product["product_name"] if product else doc["_id"]["product_id"],
                    "total_qty": doc["total_qty"],
                }

        # Premium and Bulk products by category (overall top pick)
        premium_products_by_category = {}
        bulk_products_by_category = {}
        
        tx_cursor = self.db.transactions.find(
            {"shop_id": shop_id},
            {"_id": 0, "product_id": 1, "category": 1, "amount": 1, "quantity": 1, "total_amount": 1, "purchase_qty": 1}
        )
        tx_rows = [doc async for doc in tx_cursor]
        
        prod_cursor = self.db.products.find(
            {"shop_id": shop_id},
            {"_id": 0, "product_id": 1, "product_name": 1, "product_type": 1, "is_premium": 1, "is_bulk": 1}
        )
        prod_rows = [doc async for doc in prod_cursor]
        
        if tx_rows and prod_rows:
            tx_df = pd.DataFrame(tx_rows)
            prod_df = pd.DataFrame(prod_rows)
            
            # Normalize product_type for backward compatibility
            if "product_type" not in prod_df.columns:
                prod_df["product_type"] = "daily"
                if "is_premium" in prod_df.columns:
                    prod_df.loc[prod_df["is_premium"] == True, "product_type"] = "premium"
                if "is_bulk" in prod_df.columns:
                    prod_df.loc[prod_df["is_bulk"] == True, "product_type"] = "bulk"
            else:
                prod_df["product_type"] = prod_df["product_type"].fillna("daily")
                # Also fall back to is_premium/is_bulk if product_type is daily but flags say otherwise
                if "is_premium" in prod_df.columns:
                    prod_df.loc[(prod_df["product_type"] == "daily") & (prod_df["is_premium"] == True), "product_type"] = "premium"
                if "is_bulk" in prod_df.columns:
                    prod_df.loc[(prod_df["product_type"] == "daily") & (prod_df["is_bulk"] == True), "product_type"] = "bulk"
            
            # Support both old field names (quantity/amount) and new spec names (purchase_qty/total_amount)
            if "purchase_qty" in tx_df.columns:
                tx_df["quantity"] = pd.to_numeric(tx_df["purchase_qty"], errors="coerce").fillna(1).astype(int)
            elif "quantity" in tx_df.columns:
                tx_df["quantity"] = pd.to_numeric(tx_df["quantity"], errors="coerce").fillna(1).astype(int)
            else:
                tx_df["quantity"] = 1

            if "total_amount" in tx_df.columns:
                tx_df["amount"] = pd.to_numeric(tx_df["total_amount"], errors="coerce").fillna(0)
            elif "amount" in tx_df.columns:
                tx_df["amount"] = pd.to_numeric(tx_df["amount"], errors="coerce").fillna(0)
            else:
                tx_df["amount"] = 0
            
            if not tx_df.empty and not prod_df.empty:
                cust_tx = tx_df.merge(prod_df[['product_id', 'product_name', 'product_type']], on='product_id', how='left')
                
                # Favorite Premium Product per category (highest total amount)
                premium_tx = cust_tx[cust_tx['product_type'] == 'premium']
                if not premium_tx.empty:
                    for cat, cat_df in premium_tx.groupby('category'):
                        # idxmax gives the index of the max value
                        if not cat_df.empty:
                            top_premium = cat_df.groupby('product_name')['amount'].sum().idxmax()
                            premium_products_by_category[str(cat)] = top_premium
                            
                # Favorite Bulk Product per category (highest total quantity)
                bulk_tx = cust_tx[cust_tx['product_type'] == 'bulk']
                if not bulk_tx.empty:
                    for cat, cat_df in bulk_tx.groupby('category'):
                        if not cat_df.empty:
                            top_bulk = cat_df.groupby('product_name')['quantity'].sum().idxmax()
                            bulk_products_by_category[str(cat)] = top_bulk

        # ── Customer category affinity from customer_insights ──
        total_customers = await self.db.customers.count_documents(
            {"user_id": user_id, "shop_id": shop_id}
        )
        insights_count = await self.db.customer_insights.count_documents(
            {"shop_id": shop_id}
        )
        category_affinity_pipeline = [
            {"$match": {"shop_id": shop_id}},
            {"$unwind": "$top_categories"},
            {"$group": {"_id": "$top_categories", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        affinity_cursor = self.db.customer_insights.aggregate(category_affinity_pipeline)
        customer_category_pct = {}
        async for doc in affinity_cursor:
            if insights_count > 0:
                customer_category_pct[doc["_id"]] = round(doc["count"] / insights_count * 100, 1)

        # Live stats
        active_batches = await self.db.batches.count_documents(
            {"user_id": user_id, "shop_id": shop_id, "status": {"$in": ["pending", "scheduled", "sending"]}}
        )
        batch_ids_cursor = self.db.batches.find(
            {"user_id": user_id, "shop_id": shop_id}, {"_id": 0, "id": 1}
        )
        batch_ids = [b["id"] async for b in batch_ids_cursor]
        sent_count = 0
        failed_count = 0
        pending_msg_count = 0
        if batch_ids:
            sent_count = await self.db.messages.count_documents(
                {"batch_id": {"$in": batch_ids}, "status": {"$in": ["sent", "delivered"]}}
            )
            failed_count = await self.db.messages.count_documents(
                {"batch_id": {"$in": batch_ids}, "status": {"$in": ["failed", "failed_permanently"]}}
            )
            pending_msg_count = await self.db.messages.count_documents(
                {"batch_id": {"$in": batch_ids}, "status": {"$in": ["pending", "processing", "paused"]}}
            )

        # ── Insights last calculated timestamp (Bug 3 fix) ───────────────────
        latest_insight = await self.db.customer_insights.find_one(
            {"shop_id": shop_id},
            {"_id": 0, "last_calculated_at": 1},
            sort=[("last_calculated_at", -1)],
        )
        insights_last_updated = (
            latest_insight["last_calculated_at"] if latest_insight else None
        )

        shop["csv_status"] = csv_status
        shop["customer_count"] = total_customers
        shop["product_count"] = await self.db.products.count_documents({"shop_id": shop_id})
        shop["transaction_count"] = await self.db.transactions.count_documents({"shop_id": shop_id})
        shop["segment_counts"] = segment_counts
        shop["category_breakdown"] = category_breakdown
        shop["top_products_by_category"] = top_products_by_category
        shop["premium_products_by_category"] = premium_products_by_category
        shop["bulk_products_by_category"] = bulk_products_by_category
        shop["customer_category_pct"] = customer_category_pct
        shop["insights_last_updated"] = insights_last_updated
        shop["live_stats"] = {
            "active_batches": active_batches,
            "total_campaigns": await self.db.campaigns.count_documents({"user_id": user_id, "shop_id": shop_id}),
            "sent": sent_count,
            "failed": failed_count,
            "pending": pending_msg_count,
            "total_messages": sent_count + failed_count + pending_msg_count,
        }
        return shop

    async def delete_campaign_data(self, shop_id: str, user_id: str) -> Dict[str, Any]:
        """Delete only campaign data (messages, batches, campaigns) for a shop. Keeps customer/product/transaction data."""
        batch_ids_cursor = self.db.batches.find(
            {"user_id": user_id, "shop_id": shop_id}, {"_id": 0, "id": 1}
        )
        batch_ids = [b["id"] async for b in batch_ids_cursor]

        msgs = await self.db.messages.delete_many(
            {"user_id": user_id, "batch_id": {"$in": batch_ids}} if batch_ids else {"user_id": user_id, "shop_id": shop_id}
        )
        queues = await self.db.msg_queues.delete_many(
            {"user_id": user_id, "batch_id": {"$in": batch_ids}} if batch_ids else {"user_id": user_id, "shop_id": shop_id}
        )
        cb = await self.db.campaign_batches.delete_many(
            {"user_id": user_id, "shop_id": shop_id}
        )
        batches = await self.db.batches.delete_many(
            {"user_id": user_id, "shop_id": shop_id}
        )
        campaigns = await self.db.campaigns.delete_many(
            {"user_id": user_id, "shop_id": shop_id}
        )

        return {
            "message": "Campaign data deleted successfully",
            "messages_deleted": msgs.deleted_count,
            "queues_deleted": queues.deleted_count,
            "batches_deleted": batches.deleted_count,
            "campaigns_deleted": campaigns.deleted_count,
            "campaign_batches_deleted": cb.deleted_count,
        }

    async def delete_shop(self, shop_id: str, user_id: str) -> Dict[str, Any]:
        """Delete all associated data for a shop."""
        from fastapi import HTTPException
        import asyncio

        # 1. First confirm the shop exists and is owned by this user
        shop_doc = await self.db.shops.find_one({"id": shop_id, "user_id": user_id})
        if not shop_doc:
            raise HTTPException(status_code=404, detail="Shop not found or access denied")

        # 2. Execute synchronous background deletes across all collections using shop_id
        results = await asyncio.gather(
            self.db.customers.delete_many({"shop_id": shop_id}),
            self.db.products.delete_many({"shop_id": shop_id}),
            self.db.product_inventory.delete_many({"shop_id": shop_id}),
            self.db.transactions.delete_many({"shop_id": shop_id}),
            self.db.customer_insights.delete_many({"shop_id": shop_id}),
            self.db.customer_behavior_map.delete_many({"shop_id": shop_id}),
            self.db.offers.delete_many({"shop_id": shop_id}),
            self.db.files.delete_many({"shop_id": shop_id}),
            self.db.templates.delete_many({"user_id": user_id, "shop_id": shop_id}),
            self.db.campaigns.delete_many({"user_id": user_id, "shop_id": shop_id}),
            self.db.batches.delete_many({"user_id": user_id, "shop_id": shop_id}),
            self.db.messages.delete_many({"user_id": user_id, "shop_id": shop_id}),
            self.db.msg_queues.delete_many({"user_id": user_id, "shop_id": shop_id}),
            self.db.campaign_batches.delete_many({"user_id": user_id, "shop_id": shop_id}),
            self.db.shops.delete_one({"id": shop_id, "user_id": user_id})
        )

        (
            customers,
            products,
            legacy_products,
            transactions,
            insights,
            behavior,
            offers,
            files,
            templates,
            campaigns,
            batches,
            messages,
            queues,
            cb,
            shop_del
        ) = results

        return {
            "message": "Shop and all associated data deleted permanently",
            "shop_deleted": shop_del.deleted_count,
            "customers_deleted": customers.deleted_count,
            "products_deleted": products.deleted_count + legacy_products.deleted_count,
            "transactions_deleted": transactions.deleted_count,
            "insights_deleted": insights.deleted_count,
            "behavior_maps_deleted": behavior.deleted_count,
            "offers_deleted": offers.deleted_count,
            "files_deleted": files.deleted_count,
            "templates_deleted": templates.deleted_count,
            "campaigns_deleted": campaigns.deleted_count,
            "batches_deleted": batches.deleted_count,
            "messages_deleted": messages.deleted_count,
            "queues_deleted": queues.deleted_count,
            "campaign_batches_deleted": cb.deleted_count,
        }


