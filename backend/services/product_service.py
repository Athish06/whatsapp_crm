"""
Product service for processing product CSV uploads.
Handles parsing, column mapping, and storage in product_inventory collection.
"""
import io
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase

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
            {"key": "product_name", "label": "Product Name", "description": "Used for {{offer_product_1}} and {{favorite_item}} placeholders"},
            {"key": "category", "label": "Category", "description": "Critical for Category Affinity Scoring (e.g., Grocery, Cosmetics)"},
            {"key": "price", "label": "Price", "description": "Critical for Standard Deviation math to find Premium outliers"},
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
        Parse product CSV, apply column mapping, classify product types, and upsert into MongoDB.

        Product type classification:
        - Premium: price > mean + 1 std deviation
        - Bulk: unit contains 'kg', 'pack', 'bundle', 'box', 'carton'
        - Daily: everything else

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

        # Classify product types using standard deviation
        mean_price = df["price"].mean()
        std_price = df["price"].std()
        premium_threshold = mean_price + std_price if std_price > 0 else mean_price * 1.5

        bulk_keywords = ["kg", "pack", "bundle", "box", "carton", "dozen", "liter", "litre"]

        def classify_product(row):
            if row["price"] > premium_threshold:
                return "premium"
            if any(kw in str(row["unit"]).lower() for kw in bulk_keywords):
                return "bulk"
            return "daily"

        df["product_type"] = df.apply(classify_product, axis=1)

        # Delete existing products for this shop (full replace)
        await self.db.product_inventory.delete_many({"shop_id": shop_id})

        # Prepare and insert documents
        products = []
        for _, row in df.iterrows():
            doc = {
                "shop_id": shop_id,
                "user_id": user_id,
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "category": row["category"],
                "price": float(row["price"]),
                "unit": row["unit"],
                "product_type": row["product_type"],
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            products.append(doc)

        if products:
            await self.db.product_inventory.insert_many(products)
            logger.info(f"Inserted {len(products)} products for shop {shop_id}")

        # Calculate category breakdown
        category_breakdown = df["category"].value_counts().to_dict()
        product_type_breakdown = df["product_type"].value_counts().to_dict()

        return {
            "product_count": len(products),
            "categories_found": len(category_breakdown),
            "category_breakdown": category_breakdown,
            "product_types": product_type_breakdown,
            "premium_threshold": round(premium_threshold, 2),
        }
