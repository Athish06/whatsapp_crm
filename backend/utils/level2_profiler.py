"""
Level 2 Behavioral Profiler
============================
Computes 8 per-customer template variables from transaction + product data:

    {{favorite_category}}              - Weighted affinity score (spend 50%, freq 30%, recency 20%)
    {{favorite_premium_product}}       - Highest-spend premium product in favorite_category
    {{favorite_bulk_product}}          - Highest total-quantity bulk product across all purchases
    {{second_favorite_premium_product}}- Second-highest-spend premium product
    {{recently_bought_product}}        - Product from the most recent transaction
    {{complementary_product}}          - Most co-purchased product alongside top premium/bulk product

All logic is pure pandas — no DB access here. The transaction_service passes
pre-loaded DataFrames and calls build_customer_profiles(), which returns a
list of dicts ready for insertion into customer_insights.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. PRODUCT STRATEGY — Premium & Bulk Detection
# ---------------------------------------------------------------------------

BULK_KEYWORDS = re.compile(
    r"\b(kg|kgs|ltr|litre|litres|pack|bundle|combo|family|jar|tin|sack|dozen|bulk|pouch|bag|box|crate|carton)\b",
    re.IGNORECASE,
)

BULK_UNIT_KEYWORDS = re.compile(
    r"\b(kg|kgs|ltr|litre|litres|dozen|sack)\b", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Dynamic Top N products per segment (for offer matching engine)
# ---------------------------------------------------------------------------
TOP_N_BY_SEGMENT = {
    "vip":            8,
    "loyal_frequent": 10,
    "at_risk":        5,
    "potential_bulk":  5,
    "boring":         5,
    "dormant":        5,
}
DEFAULT_TOP_N = 5


def tag_premium_products(products_df: pd.DataFrame) -> pd.DataFrame:
    """
    Mark each product as is_premium and is_luxury.

    Premium rule (per category):
        threshold = mean_price + 1.0 * std_price (with fallbacks)
        is_premium = price > threshold OR product_type == "premium"

    Luxury rule (global):
        is_luxury = price in top 5% of entire store
    """
    df = products_df.copy()
    if df.empty:
        df["is_premium"] = False
        df["is_luxury"] = False
        return df

    # Support price_per_unit (spec name), price, and unit_price (legacy names)
    if "price_per_unit" in df.columns:
        df["price"] = pd.to_numeric(df["price_per_unit"], errors="coerce").fillna(0)
    elif "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    elif "unit_price" in df.columns:
        df["price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
    else:
        df["price"] = 0

    # --- per-category premium threshold ---
    cat_stats = (
        df.groupby("category")["price"]
        .agg(["mean", "std", "count"])
        .rename(columns={"mean": "cat_mean", "std": "cat_std", "count": "cat_count"})
    )
    df = df.join(cat_stats, on="category")
    
    thresholds = []
    for _, row in df.iterrows():
        mean = row["cat_mean"]
        std = row["cat_std"]
        count = row["cat_count"]
        
        # Fallback: if category has only 1 item or prices are identical (std = 0)
        if pd.isna(std) or std == 0 or count <= 1:
            thresholds.append(mean * 1.15)
        else:
            thresholds.append(mean + 1.0 * std)
            
    df["premium_threshold"] = thresholds
    df["is_premium"] = (df["price"] > df["premium_threshold"]) | (df.get("product_type") == "premium")

    # --- global luxury: top 5% ---
    luxury_cutoff = df["price"].quantile(0.95)
    df["is_luxury"] = df["price"] >= luxury_cutoff

    return df.drop(columns=["cat_mean", "cat_std", "cat_count", "premium_threshold"], errors="ignore")


def tag_bulk_products(products_df: pd.DataFrame) -> pd.DataFrame:
    """
    Mark each product as is_bulk using a hybrid rule:
        is_bulk = keyword_match OR unit_is_bulk OR quantity_per_unit > 5 OR product_type == "bulk"
    """
    df = products_df.copy()
    if df.empty:
        df["is_bulk"] = False
        return df
    name_col = _find_col(df, ["product_name", "name", "item_name"], "")
    unit_col = _find_col(df, ["unit", "uom", "unit_of_measure"], "")
    qty_col = _find_col(df, ["quantity_per_unit", "qty_per_unit", "units_per_pack"], "")

    name_bulk = df[name_col].astype(str).str.contains(BULK_KEYWORDS) if name_col else pd.Series(False, index=df.index)
    unit_bulk = df[unit_col].astype(str).str.contains(BULK_UNIT_KEYWORDS) if unit_col else pd.Series(False, index=df.index)
    qty_bulk = (pd.to_numeric(df[qty_col], errors="coerce").fillna(0) > 5) if qty_col else pd.Series(False, index=df.index)
    
    prod_type_bulk = (df.get("product_type") == "bulk") if "product_type" in df.columns else pd.Series(False, index=df.index)

    df["is_bulk"] = name_bulk | unit_bulk | qty_bulk | prod_type_bulk
    return df



# ---------------------------------------------------------------------------
# 2. BEHAVIORAL MAPPING — Category Affinity
# ---------------------------------------------------------------------------

RECENCY_WEIGHTS = [
    (30, 1.0),    # ≤ 30 days
    (90, 0.6),    # 31–90 days
    (float("inf"), 0.2),  # > 90 days
]


def _recency_weight(days: float) -> float:
    for threshold, weight in RECENCY_WEIGHTS:
        if days <= threshold:
            return weight
    return 0.2


def compute_category_affinity(
    cust_df: pd.DataFrame,
    today: pd.Timestamp,
) -> Dict[str, float]:
    """
    Affinity(C) = 0.5 * spend_ratio(C) + 0.3 * freq_ratio(C) + 0.2 * recency_weight(C)

    recency_weight(C) = sum of per-transaction recency weights for transactions in C
    """
    if cust_df.empty:
        return {}

    total_spend = cust_df["amount"].sum()
    total_txn = len(cust_df)

    cust_df = cust_df.copy()
    cust_df["days_ago"] = (today - cust_df["purchase_date"]).dt.days.clip(lower=0)
    cust_df["rec_w"] = cust_df["days_ago"].apply(_recency_weight)

    scores: Dict[str, float] = {}
    for cat, cat_df in cust_df.groupby("category"):
        spend_ratio = cat_df["amount"].sum() / total_spend if total_spend > 0 else 0
        freq_ratio = len(cat_df) / total_txn if total_txn > 0 else 0
        recency_w = cat_df["rec_w"].sum()

        affinity = 0.5 * spend_ratio + 0.3 * freq_ratio + 0.2 * recency_w
        scores[str(cat)] = round(affinity, 4)

    return scores


# ---------------------------------------------------------------------------
# 3. PER-CUSTOMER PRODUCT VARIABLES
# ---------------------------------------------------------------------------

def _best_premium(
    cust_df: pd.DataFrame,
    product_flags: Dict[str, Dict],
    favorite_category: Optional[str],
    exclude_product: Optional[str] = None,
) -> Optional[str]:
    """Return product_name with highest spend where is_premium=True."""
    prem = cust_df[
        cust_df["product_id"].map(lambda p: product_flags.get(p, {}).get("is_premium", False))
    ]
    if favorite_category:
        prem_cat = prem[prem["category"] == favorite_category]
        if not prem_cat.empty:
            prem = prem_cat

    if exclude_product:
        prem = prem[prem["product_id"] != exclude_product]

    if prem.empty:
        return None

    best_pid = prem.groupby("product_id")["amount"].sum().idxmax()
    return product_flags.get(best_pid, {}).get("product_name", best_pid)


def _best_bulk(
    cust_df: pd.DataFrame,
    product_flags: Dict[str, Dict],
) -> Optional[str]:
    """Return product_name with highest total quantity where is_bulk=True."""
    bulk = cust_df[
        cust_df["product_id"].map(lambda p: product_flags.get(p, {}).get("is_bulk", False))
    ]
    if bulk.empty:
        return None

    best_pid = bulk.groupby("product_id")["quantity"].sum().idxmax()
    return product_flags.get(best_pid, {}).get("product_name", best_pid)


def _recently_bought(
    cust_df: pd.DataFrame,
    product_flags: Dict[str, Dict],
) -> Optional[str]:
    """Return product name from the most recent transaction row."""
    if cust_df.empty:
        return None
    latest_row = cust_df.sort_values("purchase_date", ascending=False).iloc[0]
    pid = latest_row["product_id"]
    return product_flags.get(pid, {}).get("product_name", pid)


def _complementary_product(
    cust_df: pd.DataFrame,
    anchor_product_id: Optional[str],
    all_tx_df: pd.DataFrame,
    product_flags: Dict[str, Dict],
) -> Optional[str]:
    """
    Most commonly co-purchased product with anchor_product_id (across all customers).

    Strategy:
      1. Find all transaction dates where anchor_product was bought (by any customer).
      2. On those dates find the next most-bought product (excluding anchor itself).
    """
    if anchor_product_id is None or all_tx_df.empty:
        return None

    # Dates when anchor was bought store-wide
    anchor_dates = all_tx_df[all_tx_df["product_id"] == anchor_product_id]["purchase_date"].dt.date.unique()

    if len(anchor_dates) == 0:
        return None

    # All transactions on those dates excluding the anchor
    co_tx = all_tx_df[
        (all_tx_df["purchase_date"].dt.date.isin(anchor_dates))
        & (all_tx_df["product_id"] != anchor_product_id)
    ]

    if co_tx.empty:
        return None

    # Most frequent co-purchased product
    top_pid = co_tx["product_id"].value_counts().idxmax()
    return product_flags.get(top_pid, {}).get("product_name", top_pid)


def _fallback_premium_for_category(
    cat: Optional[str],
    all_tx_df: pd.DataFrame,
    product_flags: Dict[str, Dict],
) -> Optional[str]:
    """Return the product_id of the global best-selling premium product in cat (fallback)."""
    if cat is None or all_tx_df.empty:
        return None

    cat_tx = all_tx_df[all_tx_df["category"] == cat]
    prem_tx = cat_tx[cat_tx["product_id"].map(lambda p: product_flags.get(p, {}).get("is_premium", False))]

    if prem_tx.empty:
        return None

    top_pid = prem_tx.groupby("product_id")["amount"].sum().idxmax()
    return top_pid


def _fallback_bulk_global(
    all_tx_df: pd.DataFrame,
    product_flags: Dict[str, Dict],
) -> Optional[str]:
    """Return the global highest-quantity bulk product (fallback)."""
    if all_tx_df.empty:
        return None

    bulk_tx = all_tx_df[all_tx_df["product_id"].map(lambda p: product_flags.get(p, {}).get("is_bulk", False))]
    if bulk_tx.empty:
        return None

    top_pid = bulk_tx.groupby("product_id")["quantity"].sum().idxmax()
    return product_flags.get(top_pid, {}).get("product_name", top_pid)


# ---------------------------------------------------------------------------
# 4. MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def build_customer_profiles(
    tx_df: pd.DataFrame,
    products_df: pd.DataFrame,
    shop_id: str,
    today: Optional[pd.Timestamp] = None,
    segment_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Core Level 2 profiler. Returns list of behavior_map docs (one per customer).

    Each doc contains the 8 template variables plus auxiliary fields:
        favorite_category, favorite_premium_product, favorite_bulk_product,
        second_favorite_premium_product, recently_bought_product, complementary_product,
        category_affinity_scores, fav_items, recent_purchases, top_categories,
        total_spent, total_transactions, last_purchase_date.

    Args:
        tx_df:       Transactions DataFrame with columns:
                     customer_id, product_id, purchase_date, quantity, amount, category
        products_df: Products DataFrame with columns:
                     product_id, product_name, category, price (or unit_price)
        shop_id:     Shop identifier for scoping DB docs.
        today:       Reference timestamp (defaults to now).
    """
    if today is None:
        today = pd.Timestamp.now()

    if tx_df.empty:
        logger.warning("No transactions provided to Level 2 profiler.")
        return []

    # ---- Tag products ----
    tagged = tag_premium_products(products_df)
    tagged = tag_bulk_products(tagged)

    # Build fast lookup: product_id → {product_name, is_premium, is_bulk, is_luxury}
    product_flags: Dict[str, Dict] = {}
    for _, row in tagged.iterrows():
        pid = str(row["product_id"])
        name_col = _find_col(tagged, ["product_name", "name", "item_name"], "")
        product_flags[pid] = {
            "product_name": str(row[name_col]) if name_col else pid,
            "is_premium": bool(row.get("is_premium", False)),
            "is_bulk": bool(row.get("is_bulk", False)),
            "is_luxury": bool(row.get("is_luxury", False)),
        }

    # Ensure purchase_date is datetime
    tx_df = tx_df.copy()
    tx_df["purchase_date"] = pd.to_datetime(tx_df["purchase_date"], errors="coerce")
    tx_df = tx_df.dropna(subset=["purchase_date"])

    all_tx_df = tx_df  # reference for co-purchase analysis

    docs: List[Dict[str, Any]] = []

    for cust_id, cust_df in tx_df.groupby("customer_id"):
        cust_df = cust_df.copy()

        # ---- Category Affinity ----
        affinity_scores = compute_category_affinity(cust_df, today)

        favorite_category: Optional[str] = None
        if affinity_scores:
            favorite_category = max(affinity_scores, key=lambda k: affinity_scores[k])

        # ---- Top categories (for backward compat) ----
        cat_spend = cust_df.groupby("category")["amount"].sum().sort_values(ascending=False)
        top_categories = cat_spend.head(3).index.tolist()

        # ---- Favorite premium products ----
        fav_prem_pid: Optional[str] = None
        fav_prem_name: Optional[str] = None

        prem_rows = cust_df[cust_df["product_id"].map(
            lambda p: product_flags.get(p, {}).get("is_premium", False)
        )]
        # Prefer products in favorite_category first
        prem_in_fav = prem_rows[prem_rows["category"] == favorite_category] if favorite_category else pd.DataFrame()
        search_rows = prem_in_fav if not prem_in_fav.empty else prem_rows

        if not search_rows.empty:
            by_spend = search_rows.groupby("product_id")["amount"].sum().sort_values(ascending=False)
            fav_prem_pid = by_spend.index[0]
            fav_prem_name = product_flags.get(fav_prem_pid, {}).get("product_name", fav_prem_pid)
        else:
            # Fallback: global best premium in favorite category
            fav_prem_pid = _fallback_premium_for_category(favorite_category, all_tx_df, product_flags)
            if fav_prem_pid:
                fav_prem_name = product_flags.get(fav_prem_pid, {}).get("product_name", fav_prem_pid)

        # Fallback if no premium product in favorite category exists
        if fav_prem_name is None:
            # Try global premium fallback across the entire shop
            global_prem_tx = all_tx_df[all_tx_df["product_id"].map(lambda p: product_flags.get(p, {}).get("is_premium", False))]
            if not global_prem_tx.empty:
                fav_prem_pid = global_prem_tx.groupby("product_id")["amount"].sum().idxmax()
                fav_prem_name = product_flags.get(fav_prem_pid, {}).get("product_name", fav_prem_pid)
            
            # Ultimate fallback: overall best-selling product in their favorite category (even if not premium)
            if fav_prem_name is None and favorite_category:
                cat_tx = all_tx_df[all_tx_df["category"] == favorite_category]
                if not cat_tx.empty:
                    fav_prem_pid = cat_tx.groupby("product_id")["amount"].sum().idxmax()
                    fav_prem_name = product_flags.get(fav_prem_pid, {}).get("product_name", fav_prem_pid)
            
            # Ultimate ultimate fallback: overall best-selling product across the entire store
            if fav_prem_name is None and not all_tx_df.empty:
                fav_prem_pid = all_tx_df.groupby("product_id")["amount"].sum().idxmax()
                fav_prem_name = product_flags.get(fav_prem_pid, {}).get("product_name", fav_prem_pid)

        # ---- Second favorite premium ----
        second_prem_name: Optional[str] = None
        if not search_rows.empty:
            by_spend = search_rows.groupby("product_id")["amount"].sum().sort_values(ascending=False)
            if len(by_spend) >= 2:
                second_pid = by_spend.index[1]
                second_prem_name = product_flags.get(second_pid, {}).get("product_name", second_pid)
            elif fav_prem_pid:
                # Try other categories for 2nd premium
                other_prem = prem_rows[prem_rows["product_id"] != fav_prem_pid]
                if not other_prem.empty:
                    s_pid = other_prem.groupby("product_id")["amount"].sum().idxmax()
                    second_prem_name = product_flags.get(s_pid, {}).get("product_name", s_pid)

        if second_prem_name is None:
            # Fallback to the second global best-selling premium product in their favorite category
            if favorite_category:
                cat_tx = all_tx_df[all_tx_df["category"] == favorite_category]
                prem_cat_tx = cat_tx[cat_tx["product_id"].map(lambda p: product_flags.get(p, {}).get("is_premium", False))]
                if fav_prem_pid:
                    prem_cat_tx = prem_cat_tx[prem_cat_tx["product_id"] != fav_prem_pid]
                if not prem_cat_tx.empty:
                    top_pid = prem_cat_tx.groupby("product_id")["amount"].sum().idxmax()
                    second_prem_name = product_flags.get(top_pid, {}).get("product_name", top_pid)
            
            # If STILL None, fallback to the second global best-selling premium product across the store
            if second_prem_name is None:
                global_prem_tx = all_tx_df[all_tx_df["product_id"].map(lambda p: product_flags.get(p, {}).get("is_premium", False))]
                if fav_prem_pid:
                    global_prem_tx = global_prem_tx[global_prem_tx["product_id"] != fav_prem_pid]
                if not global_prem_tx.empty:
                    top_pid = global_prem_tx.groupby("product_id")["amount"].sum().idxmax()
                    second_prem_name = product_flags.get(top_pid, {}).get("product_name", top_pid)

            # Ultimate fallback if NO premium products exist in the database
            if second_prem_name is None and not all_tx_df.empty:
                global_tx = all_tx_df
                if fav_prem_pid:
                    global_tx = global_tx[global_tx["product_id"] != fav_prem_pid]
                if not global_tx.empty:
                    top_pid = global_tx.groupby("product_id")["amount"].sum().idxmax()
                    second_prem_name = product_flags.get(top_pid, {}).get("product_name", top_pid)

        # ---- Favorite bulk product ----
        bulk_name = _best_bulk(cust_df, product_flags)
        # Capture bulk product ID for matching engine
        bulk_pid = None
        bulk_rows_for_pid = cust_df[cust_df["product_id"].map(
            lambda p: product_flags.get(p, {}).get("is_bulk", False)
        )]
        if not bulk_rows_for_pid.empty:
            bulk_pid = bulk_rows_for_pid.groupby("product_id")["quantity"].sum().idxmax()
        if bulk_name is None:
            bulk_name = _fallback_bulk_global(all_tx_df, product_flags)

        # ---- Top N product IDs for offer matching engine ----
        cust_segment = segment_map.get(str(cust_id), "boring") if segment_map else "boring"
        n_products = TOP_N_BY_SEGMENT.get(cust_segment, DEFAULT_TOP_N)
        all_product_counts = cust_df.groupby("product_id")["quantity"].sum().sort_values(ascending=False)
        exclude_pids = {fav_prem_pid, bulk_pid} - {None}
        top_n_product_ids = [pid for pid in all_product_counts.index if pid not in exclude_pids][:n_products]

        # ---- Recently bought ----
        recent_name = _recently_bought(cust_df, product_flags)

        # ---- Complementary product ----
        # Anchor = favorite_premium_product's product_id (or favorite bulk product)
        anchor_pid = fav_prem_pid
        if anchor_pid is None:
            # Try to get anchor from bulk
            bulk_rows = cust_df[cust_df["product_id"].map(
                lambda p: product_flags.get(p, {}).get("is_bulk", False)
            )]
            if not bulk_rows.empty:
                anchor_pid = bulk_rows.groupby("product_id")["quantity"].sum().idxmax()

        # If STILL None, use their most purchased product as anchor!
        if anchor_pid is None and not cust_df.empty:
            anchor_pid = cust_df.groupby("product_id")["quantity"].sum().idxmax()

        complementary_name = _complementary_product(cust_df, anchor_pid, all_tx_df, product_flags)
        if complementary_name is None:
            # Fallback to the overall best-selling product in their favorite category (excluding anchor)
            if favorite_category:
                cat_tx = all_tx_df[all_tx_df["category"] == favorite_category]
                if anchor_pid:
                    cat_tx = cat_tx[cat_tx["product_id"] != anchor_pid]
                if not cat_tx.empty:
                    top_pid = cat_tx.groupby("product_id")["quantity"].sum().idxmax()
                    complementary_name = product_flags.get(top_pid, {}).get("product_name", top_pid)
            
            # If STILL None, fallback to global top product in the shop (excluding anchor)
            if complementary_name is None and not all_tx_df.empty:
                global_tx = all_tx_df
                if anchor_pid:
                    global_tx = global_tx[global_tx["product_id"] != anchor_pid]
                if not global_tx.empty:
                    top_pid = global_tx.groupby("product_id")["quantity"].sum().idxmax()
                    complementary_name = product_flags.get(top_pid, {}).get("product_name", top_pid)

        # ---- Fav items (top 5 by total quantity, backward compat) ----
        fav_items_series = cust_df.groupby("product_id")["quantity"].sum().sort_values(ascending=False).head(5)
        fav_items = [
            {
                "product_id": pid,
                "product_name": product_flags.get(pid, {}).get("product_name", pid),
                "total_qty": int(qty),
            }
            for pid, qty in fav_items_series.items()
        ]

        # ---- Recent purchases (last 10 unique products, backward compat) ----
        sorted_cust = cust_df.sort_values("purchase_date", ascending=False)
        recent_pids = sorted_cust["product_id"].unique()[:10].tolist()
        recent_purchases = [
            {
                "product_id": pid,
                "product_name": product_flags.get(pid, {}).get("product_name", pid),
            }
            for pid in recent_pids
        ]

        # ---- Aggregate stats ----
        total_spent = float(cust_df["amount"].sum())
        total_transactions = len(cust_df)
        last_purchase = sorted_cust["purchase_date"].iloc[0] if len(sorted_cust) > 0 else None

        doc = {
            "shop_id": shop_id,
            "customer_id": str(cust_id),
            # ===== 8 TEMPLATE VARIABLES =====
            "favorite_category": favorite_category,
            "favorite_premium_product": fav_prem_name,
            "favorite_bulk_product": bulk_name,
            "second_favorite_premium_product": second_prem_name,
            "recently_bought_product": recent_name,
            "complementary_product": complementary_name,
            # ===== MATCHING ENGINE FIELDS =====
            "favorite_premium_product_id": fav_prem_pid,
            "favorite_bulk_product_id": bulk_pid,
            "top_n_product_ids": top_n_product_ids,
            # ================================
            "category_affinity_scores": affinity_scores,
            # Backward-compat fields
            "fav_items": fav_items,
            "recent_purchases": recent_purchases,
            "top_categories": top_categories,
            "total_spent": total_spent,
            "total_transactions": total_transactions,
            "last_purchase_date": last_purchase,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        docs.append(doc)

    logger.info(f"[Level2] Built profiles for {len(docs)} customers in shop {shop_id}")
    return docs


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_col(df: pd.DataFrame, candidates: List[str], default: str) -> str:
    """Return the first matching column name from candidates, or default."""
    for col in candidates:
        if col in df.columns:
            return col
    return default
