"""
Transaction service for processing transaction CSV uploads.
Handles parsing, storage, and triggering insight recalculation.
"""
import io
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

import pandas as pd
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class TransactionService:
    """Service for transaction data operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    @staticmethod
    def get_required_columns() -> List[Dict[str, str]]:
        """Return the required columns for transaction CSV."""
        return [
            {"key": "customer_id", "label": "Customer ID / Phone", "description": "Must match phone or id in the Customer file"},
            {"key": "product_id", "label": "Product ID", "description": "Must match product_id in the Product file"},
            {"key": "purchase_date", "label": "Purchase Date", "description": "Critical for Recency Weighting (YYYY-MM-DD format)"},
            {"key": "quantity", "label": "Quantity", "description": "Used to identify Bulk behavior (buying 50 vs 1 unit)"},
            {"key": "amount", "label": "Amount", "description": "Total spend per transaction to verify spend per category"},
        ]

    async def process_transactions(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        shop_id: str,
        column_mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Parse transaction CSV, store in transactions collection,
        and trigger full insight recalculation (RFM + Level 2).

        Returns:
            Dict with transaction_count, categories_found, top_products_per_category,
            customer_category_percentages
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
        required = ["customer_id", "product_id", "purchase_date", "quantity", "amount"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns after mapping: {', '.join(missing)}")

        # Clean data
        df["customer_id"] = df["customer_id"].astype(str).str.strip()
        df["product_id"] = df["product_id"].astype(str).str.strip()
        df["purchase_date"] = pd.to_datetime(df["purchase_date"], errors="coerce")
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1).astype(int)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

        # Drop rows with missing critical data
        df = df.dropna(subset=["purchase_date"])
        df = df[df["customer_id"].str.len() > 0]
        df = df[df["product_id"].str.len() > 0]

        # Look up product categories from product_inventory
        product_ids = df["product_id"].unique().tolist()
        products_cursor = self.db.product_inventory.find(
            {"shop_id": shop_id, "product_id": {"$in": product_ids}},
            {"_id": 0, "product_id": 1, "category": 1, "product_name": 1},
        )
        product_map = {}
        async for p in products_cursor:
            product_map[p["product_id"]] = p

        # Enrich transactions with category
        df["category"] = df["product_id"].map(
            lambda pid: product_map.get(pid, {}).get("category", "Unknown")
        )

        # Delete existing transactions for this shop (full replace)
        await self.db.transactions.delete_many({"shop_id": shop_id})

        # Prepare and insert transaction documents
        tx_docs = []
        for _, row in df.iterrows():
            doc = {
                "shop_id": shop_id,
                "user_id": user_id,
                "customer_id": str(row["customer_id"]),
                "product_id": str(row["product_id"]),
                "category": row["category"],
                "purchase_date": row["purchase_date"],
                "quantity": int(row["quantity"]),
                "amount": float(row["amount"]),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            tx_docs.append(doc)

        if tx_docs:
            await self.db.transactions.insert_many(tx_docs)
            logger.info(f"Inserted {len(tx_docs)} transactions for shop {shop_id}")

        # ── Trigger full insight recalculation (RFM + Level 2) ──
        from services.insights_service import recalculate_all_insights
        insights_count = await recalculate_all_insights(self.db, shop_id)
        logger.info(f"Recalculated {insights_count} customer insights after transaction upload")

        # Calculate response insights
        categories_found = df["category"].nunique()

        # Top product per category (by total quantity)
        top_per_cat = {}
        for cat in df["category"].unique():
            cat_df = df[df["category"] == cat]
            top_product_id = cat_df.groupby("product_id")["quantity"].sum().idxmax()
            prod_info = product_map.get(top_product_id, {})
            top_per_cat[cat] = {
                "product_id": top_product_id,
                "product_name": prod_info.get("product_name", top_product_id),
                "total_qty": int(cat_df[cat_df["product_id"] == top_product_id]["quantity"].sum()),
            }

        # Customer category percentages
        total_unique_customers = df["customer_id"].nunique()
        cat_customer_counts = {}
        for cat in df["category"].unique():
            cat_customers = df[df["category"] == cat]["customer_id"].nunique()
            cat_customer_counts[cat] = round(cat_customers / total_unique_customers * 100, 1) if total_unique_customers > 0 else 0

        return {
            "transaction_count": len(tx_docs),
            "categories_found": categories_found,
            "top_products_per_category": top_per_cat,
            "customer_category_pct": cat_customer_counts,
            "unique_customers": total_unique_customers,
            "insights_generated": insights_count,
        }


async def regenerate_level2_profiles(db: AsyncIOMotorDatabase, shop_id: str) -> int:
    """
    On-demand re-run of full insight pipeline from existing transactions + products.
    Useful for triggering after a product catalog update without re-uploading transactions.

    Returns number of customer profiles generated.
    """
    from services.insights_service import recalculate_all_insights
    return await recalculate_all_insights(db, shop_id)
