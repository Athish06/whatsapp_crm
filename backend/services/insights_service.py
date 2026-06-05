"""
Customer Insights Service
==========================
Computes and caches ALL derived customer intelligence in one place:
  - Level 1: RFM scores + segment classification
  - Level 2: Behavioral profiling (favorite_category, premium/bulk products, etc.)

The customer_insights collection is the SINGLE SOURCE OF TRUTH for all computed
customer data. It can be safely deleted and regenerated from raw transactions.

Per schema spec:
  - Reads 'purchase_qty' and 'total_amount' from transactions (renamed fields)
  - Stores 'recency_days' (renamed from 'recency')
  - Stores 'updated_at' timestamp
  - Does NOT write back to customers collection (customers = identity only)

Usage:
    await recalculate_all_insights(db, shop_id)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase

from utils.level2_profiler import build_customer_profiles
from schemas import CustomerCategory

logger = logging.getLogger(__name__)


async def recalculate_all_insights(db: AsyncIOMotorDatabase, shop_id: str) -> int:
    """
    Master insight computation pipeline.

    Steps:
        1. Load all transactions for the shop into RAM.
        2. Load all products for the shop.
        3. Compute foundational metrics per customer_id (R, F, M, qty, purchase_count).
        4. Run Level 1 RFM quintile scoring + waterfall segmentation.
        5. Run Level 2 behavioral profiling (category affinity, premium/bulk picks).
        6. Merge both into a single document per customer and upsert into customer_insights.

    Returns:
        Number of customer insight documents written.
    """
    # ── Step 1: Load transactions ──────────────────────────────────────────
    tx_cursor = db.transactions.find({"shop_id": shop_id}, {"_id": 0})
    tx_rows = [doc async for doc in tx_cursor]

    if not tx_rows:
        logger.warning(f"[Insights] No transactions found for shop {shop_id}")
        # Clear stale insights if transactions were removed
        await db.customer_insights.delete_many({"shop_id": shop_id})
        return 0

    tx_df = pd.DataFrame(tx_rows)
    tx_df["purchase_date"] = pd.to_datetime(tx_df["purchase_date"], errors="coerce")
    tx_df = tx_df.dropna(subset=["purchase_date"])

    # ── Support both old field names (quantity/amount) and new spec names (purchase_qty/total_amount)
    # This ensures the pipeline works regardless of which upload version created the transactions.
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

    if tx_df.empty:
        await db.customer_insights.delete_many({"shop_id": shop_id})
        return 0

    # ── Step 2: Load products ──────────────────────────────────────────────
    prod_cursor = db.product_inventory.find(
        {"shop_id": shop_id},
        {"_id": 0, "product_id": 1, "product_name": 1, "category": 1,
         "price_per_unit": 1, "price": 1, "unit": 1,
         "is_premium": 1, "is_bulk": 1, "product_type": 1},
    )
    prod_rows = [doc async for doc in prod_cursor]
    products_df = pd.DataFrame(prod_rows) if prod_rows else pd.DataFrame(
        columns=["product_id", "product_name", "category", "price_per_unit", "product_type"]
    )

    # Normalise price column: support both price_per_unit (new) and price (legacy)
    if "price_per_unit" in products_df.columns:
        products_df["price"] = pd.to_numeric(products_df["price_per_unit"], errors="coerce").fillna(0)
    elif "price" not in products_df.columns:
        products_df["price"] = 0

    # ── Step 3: Compute foundational metrics per customer ──────────────────
    today = pd.Timestamp.now()

    agg_df = tx_df.groupby("customer_id").agg(
        recency_date=("purchase_date", "max"),
        frequency=("purchase_date", lambda x: x.dt.date.nunique()),
        monetary=("amount", "sum"),
        purchase_count=("purchase_date", "count"),  # total transaction rows
        total_quantity=("quantity", "sum"),
    ).reset_index()

    agg_df["recency_days"] = (today - agg_df["recency_date"]).dt.days.clip(lower=0)
    agg_df["recency_raw"] = agg_df["recency_days"]

    # Bulkiness = avg items per transaction row
    agg_df["bulkiness"] = (agg_df["total_quantity"] / agg_df["purchase_count"]).fillna(0)

    # ── Step 4: Level 1 — RFM Quintile Scoring ────────────────────────────
    agg_df = _compute_rfm_scores(agg_df)

    # Store average bulkiness for waterfall
    store_avg_bulkiness = agg_df["bulkiness"].mean()

    # Waterfall segmentation
    agg_df["segment"] = agg_df.apply(
        lambda row: _waterfall_segment(row, store_avg_bulkiness), axis=1
    )

    # ── Step 5: Level 2 — Behavioral Profiling ────────────────────────────
    behavior_docs = build_customer_profiles(
        tx_df=tx_df,
        products_df=products_df,
        shop_id=shop_id,
        today=today,
    )

    # Index behavior by customer_id for fast merge
    behavior_map: Dict[str, Dict] = {}
    for bdoc in behavior_docs:
        behavior_map[bdoc["customer_id"]] = bdoc

    # ── Step 6: Merge & Persist ────────────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()
    insight_docs: List[Dict[str, Any]] = []

    for _, row in agg_df.iterrows():
        cust_id = str(row["customer_id"])
        behavior = behavior_map.get(cust_id, {})

        doc = {
            "shop_id": shop_id,
            "customer_id": cust_id,

            # ── Level 1 — RFM ──
            "recency_days": int(row["recency_days"]),    # renamed per spec (was 'recency')
            "frequency": int(row["frequency"]),
            "monetary": float(row["monetary"]),
            "purchase_count": int(row["purchase_count"]),
            "total_quantity": int(row["total_quantity"]),

            # ── Level 1 Scores ──
            "r_score": int(row["r_score"]),
            "f_score": int(row["f_score"]),
            "m_score": int(row["m_score"]),
            "rfm_score": int(row["rfm_score"]),
            "segment": row["segment"],

            # ── Level 2 Classifications ──
            "favorite_category": behavior.get("favorite_category"),
            "favorite_premium_product": behavior.get("favorite_premium_product"),
            "favorite_bulk_product": behavior.get("favorite_bulk_product"),
            "second_favorite_premium_product": behavior.get("second_favorite_premium_product"),
            "recently_bought_product": behavior.get("recently_bought_product"),
            "complementary_product": behavior.get("complementary_product"),

            # ── Analytics extras ──
            "category_affinity_scores": behavior.get("category_affinity_scores", {}),
            "fav_items": behavior.get("fav_items", []),
            "recent_purchases": behavior.get("recent_purchases", []),
            "top_categories": behavior.get("top_categories", []),
            "total_spent": behavior.get("total_spent", float(row["monetary"])),
            "total_transactions": behavior.get("total_transactions", int(row["purchase_count"])),
            "last_purchase_date": behavior.get("last_purchase_date"),

            # ── Metadata ──
            "last_calculated_at": now_iso,
            "updated_at": now_iso,                        # NEW per spec
        }
        insight_docs.append(doc)

    # Atomic replace: delete old → insert new
    await db.customer_insights.delete_many({"shop_id": shop_id})
    if insight_docs:
        await db.customer_insights.insert_many(insight_docs)
        logger.info(
            f"[Insights] Stored {len(insight_docs)} customer insights for shop {shop_id}"
        )

    # NOTE: We do NOT write back to customers collection.
    # Per schema spec: customers = identity only (name, phone, city, etc.)
    # All RFM / segment data lives exclusively in customer_insights.
    # batch_service.py already has an insights_segment_map fallback that reads
    # directly from customer_insights for priority routing.

    return len(insight_docs)


# ────────────────────────────────────────────────────────────────────────────
# Private helpers
# ────────────────────────────────────────────────────────────────────────────

def _compute_rfm_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute R, F, M quintile scores (1-5) using rank-based method."""

    # ── Recency Score (lower days = better = 5) ──
    df["recency_rank"] = df["recency_raw"].rank(method="average")
    df["r_score"] = _safe_qcut(df["recency_rank"], labels_asc=[5, 4, 3, 2, 1])

    # ── Frequency Score (higher = better = 5) ──
    df["f_rank"] = df["frequency"].rank(method="average")
    df["f_score"] = _safe_qcut(df["f_rank"], labels_asc=[1, 2, 3, 4, 5])

    # ── Monetary Score (log-damped, higher = better = 5) ──
    df["monetary_log"] = np.log1p(df["monetary"])
    df["m_rank"] = df["monetary_log"].rank(method="average")
    df["m_score"] = _safe_qcut(df["m_rank"], labels_asc=[1, 2, 3, 4, 5])

    # Force int
    for col in ["r_score", "f_score", "m_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(3).astype(int)

    df["rfm_score"] = df["r_score"] + df["f_score"] + df["m_score"]
    df["rfm_score"] = pd.to_numeric(df["rfm_score"], errors="coerce").fillna(9).astype(int)

    return df


def _safe_qcut(series: pd.Series, labels_asc: list, q: int = 5) -> pd.Series:
    """Robust quintile cut with fallback to pd.cut and then constant."""
    try:
        return pd.qcut(series, q=q, labels=labels_asc, duplicates="drop").astype(int)
    except (ValueError, TypeError):
        try:
            return pd.cut(series, bins=q, labels=labels_asc, include_lowest=True).astype(int)
        except Exception:
            return pd.Series(3, index=series.index)


def _waterfall_segment(row, store_avg_bulkiness: float) -> str:
    """5-tier waterfall decision tree — identical to classifier.py logic."""
    total = row["rfm_score"]
    r = row["r_score"]
    f = row["f_score"]
    m = row["m_score"]
    bulk = row["bulkiness"]

    if total >= 12:
        return CustomerCategory.VIP.value
    if r == 1 and total > 4:
        return CustomerCategory.AT_RISK.value
    if 5 <= total <= 11 and bulk > store_avg_bulkiness:
        return CustomerCategory.POTENTIAL_BULK.value
    if 5 <= total <= 11 and f >= m:
        return CustomerCategory.LOYAL_FREQUENT.value
    return CustomerCategory.BORING.value


async def migrate_behavior_to_insights(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    One-time migration: copies all behavioral fields from the legacy
    customer_behavior_map collection into customer_insights.
    After successful migration, drops customer_behavior_map.
    """
    # Check if the old collection exists and has documents
    collections = await db.list_collection_names()
    if "customer_behavior_map" not in collections:
        logger.info("[Migration] customer_behavior_map collection does not exist. Skipping migration.")
        return {"migrated": 0, "status": "skipped_no_collection"}

    count = await db.customer_behavior_map.count_documents({})
    if count == 0:
        logger.info("[Migration] customer_behavior_map is empty. Dropping empty collection.")
        try:
            await db.customer_behavior_map.drop()
            logger.info("[Migration] customer_behavior_map collection dropped.")
        except Exception as e:
            logger.error(f"[Migration] Failed to drop customer_behavior_map: {e}")
        return {"migrated": 0, "status": "dropped_empty"}

    logger.info(f"[Migration] Starting migration of {count} documents from customer_behavior_map to customer_insights...")

    from pymongo import UpdateOne
    ops = []
    migrated_count = 0

    cursor = db.customer_behavior_map.find({})
    async for bdoc in cursor:
        shop_id = bdoc.get("shop_id")
        customer_id = bdoc.get("customer_id")
        if not shop_id or not customer_id:
            continue

        # Prepare update doc with all behavioral fields
        set_fields = {}
        behavioral_keys = [
            "favorite_category", "favorite_premium_product", "favorite_bulk_product",
            "second_favorite_premium_product", "recently_bought_product", "complementary_product",
            "category_affinity_scores", "fav_items", "recent_purchases", "top_categories",
            "total_spent", "total_transactions", "last_purchase_date"
        ]
        for key in behavioral_keys:
            if key in bdoc and bdoc[key] is not None:
                set_fields[key] = bdoc[key]

        if not set_fields:
            continue

        ops.append(
            UpdateOne(
                {"shop_id": shop_id, "customer_id": customer_id},
                {
                    "$set": set_fields,
                    "$setOnInsert": {
                        "segment": bdoc.get("segment", "boring"),
                        "recency_days": 0,
                        "frequency": 1,
                        "monetary": float(bdoc.get("total_spent", 0)),
                        "purchase_count": int(bdoc.get("total_transactions", 1)),
                        "total_quantity": 1,
                        "r_score": 3,
                        "f_score": 3,
                        "m_score": 3,
                        "rfm_score": 9,
                        "last_calculated_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True
            )
        )
        migrated_count += 1

    if ops:
        await db.customer_insights.bulk_write(ops, ordered=False)
        logger.info(f"[Migration] Successfully migrated {migrated_count} documents to customer_insights.")

    # Drop the collection
    try:
        await db.customer_behavior_map.drop()
        logger.info("[Migration] Legacy customer_behavior_map collection dropped successfully.")
    except Exception as e:
        logger.error(f"[Migration] Failed to drop customer_behavior_map after migration: {e}")
        return {"migrated": migrated_count, "status": f"migration_done_drop_failed: {e}"}

    return {"migrated": migrated_count, "status": "completed"}
