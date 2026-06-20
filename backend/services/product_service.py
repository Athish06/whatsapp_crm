"""
Product service for processing product CSV uploads.
Per schema spec:
  - price_per_unit (renamed from price)
  - is_premium (bool)
  - is_bulk (bool)
  - product_type kept for backward compat with level2_profiler
"""
import io
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

logger = logging.getLogger(__name__)


class ProductService:
    """Service for product inventory operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    @staticmethod
    def get_required_columns() -> List[Dict[str, str]]:
        """Return the required columns for product CSV."""
        return [
            {"key": "product_id", "label": "Product ID", "description": "Unique product identifier — links to Transaction file"},
            {"key": "product_name", "label": "Product Name", "description": "Used for {{favorite_premium_product}} and {{favorite_bulk_product}} placeholders"},
            {"key": "category", "label": "Category", "description": "Critical for Category Affinity Scoring (e.g., Grocery, Cosmetics)"},
            {"key": "price", "label": "Price / Unit Price", "description": "Critical for Standard Deviation math to find Premium outliers (stored as price_per_unit)"},
            {"key": "unit", "label": "Unit", "description": "To identify Bulk items (scans for kg, pack, bundle, etc.)"},
        ]

    async def process_products(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        shop_id: str,
        column_mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Parse product CSV, apply column mapping, classify product types,
        and upsert into MongoDB.

        Product type classification (per spec):
        - Premium: price_per_unit > mean + 1 std deviation (per category)
        - Bulk:    unit contains bulk keywords (kg, pack, bundle, box, carton…)
        - Daily:   everything else

        Stores:
            product_id, shop_id, user_id, product_name, category,
            price_per_unit, unit, is_premium (bool), is_bulk (bool),
            product_type (str, for backward compat), uploaded_at

        Returns:
            Dict with product_count, categories_found, category_breakdown, product_types
        """
        # Parse file
        filename_lower = filename.lower()
        if filename_lower.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_content))
        elif filename_lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError("Unsupported file format. Use CSV or Excel.")

        # Apply column mapping
        reverse_map = {v: k for k, v in column_mapping.items() if v and v != "none"}
        df = df.rename(columns=reverse_map)

        # Validate required columns
        required = ["product_id", "product_name", "category", "price", "unit"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns after mapping: {', '.join(missing)}")

        # Clean data
        df["product_id"] = df["product_id"].astype(str).str.strip()
        df["product_name"] = df["product_name"].astype(str).str.strip()
        df["category"] = df["category"].astype(str).str.strip()
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
        df["unit"] = df["unit"].astype(str).str.strip().str.lower()

        # Drop rows with empty product_id
        df = df[df["product_id"].str.len() > 0]

        # ── Premium Classification (per-category std dev) ──────────────────
        # Compute per-category mean/std for more accurate thresholds
        cat_stats = df.groupby("category")["price"].agg(["mean", "std"]).reset_index()
        cat_stats.columns = ["category", "cat_mean", "cat_std"]
        df = df.merge(cat_stats, on="category", how="left")

        def _premium_threshold(row):
            std = row["cat_std"]
            mean = row["cat_mean"]
            if pd.isna(std) or std == 0:
                return mean * 1.15
            return mean + 1.0 * std

        df["premium_threshold"] = df.apply(_premium_threshold, axis=1)

        # ── Bulk Classification ────────────────────────────────────────────
        bulk_keywords = ["kg", "kgs", "pack", "bundle", "box", "carton", "dozen",
                         "liter", "litre", "litres", "sack", "pouch", "crate"]

        def classify_product(row):
            is_prem = row["price"] > row["premium_threshold"]
            is_blk = any(kw in str(row["unit"]).lower() for kw in bulk_keywords)
            # product_type string for level2_profiler backward compat
            if is_prem:
                ptype = "premium"
            elif is_blk:
                ptype = "bulk"
            else:
                ptype = "daily"
            return is_prem, is_blk, ptype

        results = df.apply(classify_product, axis=1, result_type="expand")
        df["is_premium"] = results[0]
        df["is_bulk"] = results[1]
        df["product_type"] = results[2]

        # Drop helper columns
        df = df.drop(columns=["cat_mean", "cat_std", "premium_threshold"], errors="ignore")

        # Products are upserted by (shop_id, product_id) — existing catalog is preserved.
        # Re-uploading a smaller file only updates/adds those rows, never deletes others.

        # Prepare documents
        products = []
        uploaded_at = datetime.now(timezone.utc).isoformat()
        for _, row in df.iterrows():
            doc = {
                "shop_id": shop_id,
                "user_id": user_id,
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "category": row["category"],
                "price_per_unit": float(row["price"]),   # renamed per spec
                "unit": row["unit"],
                "is_premium": bool(row["is_premium"]),    # explicit boolean
                "is_bulk": bool(row["is_bulk"]),          # explicit boolean
                "product_type": row["product_type"],      # kept for level2_profiler compat
                "uploaded_at": uploaded_at,
            }
            products.append(doc)

        if products:
            # Upsert by (shop_id, product_id) — never wipe the existing catalog
            ops = [
                UpdateOne(
                    {"shop_id": doc["shop_id"], "product_id": doc["product_id"]},
                    {"$set": doc},
                    upsert=True
                )
                for doc in products
            ]
            await self.db.product_inventory.bulk_write(ops, ordered=False)
            logger.info(f"Upserted {len(products)} products for shop {shop_id}")

        # Calculate category breakdown
        category_breakdown = df["category"].value_counts().to_dict()
        product_type_breakdown = df["product_type"].value_counts().to_dict()
        premium_threshold_global = float(df["price"].mean() + df["price"].std()) if len(df) > 1 else float(df["price"].mean())

        return {
            "product_count": len(products),
            "categories_found": len(category_breakdown),
            "category_breakdown": category_breakdown,
            "product_types": product_type_breakdown,
            "premium_threshold": round(premium_threshold_global, 2),
        }
