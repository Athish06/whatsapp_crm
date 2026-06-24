"""
Offers Service — Phase 3

Provides full offer lifecycle management and the Composite Affinity Rank engine
that matches each customer to their best-scoring active offer.

Mathematical Model:
    Affinity(c, o) = S(c, o) × [1.0 + P(c, o)]
    where:
        S(c, o) = 1  if customer segment ∈ offer.target_segments, else 0
        P(c, o) = w1 × I(product_match) + w2 × I(category_match)
        w1 = 3.0  (exact product hit)
        w2 = 1.0  (category hit)

Best offer per customer = argmax over all active offers.
"""
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)

# ── Affinity weight constants ─────────────────────────────────────────────────
W_PRODUCT  = 3.0   # exact product match bonus
W_CATEGORY = 1.0   # category-wide match bonus


class OffersService:
    """Service for offer lifecycle and affinity-based customer–offer matching."""

    def __init__(self, db: Any):
        self.db = db

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD
    # ═══════════════════════════════════════════════════════════════════════════

    async def create_offer(
        self,
        shop_id: str,
        user_id: str,
        offer_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new offer document in the offers collection."""
        now = datetime.now(timezone.utc).isoformat()
        offer_id = str(uuid.uuid4())

        # Normalise date fields to ISO strings
        valid_from = offer_data.get("valid_from")
        valid_until = offer_data.get("valid_until")
        if isinstance(valid_from, date):
            valid_from = valid_from.isoformat()
        if isinstance(valid_until, date):
            valid_until = valid_until.isoformat()

        doc = {
            "id":              offer_id,
            "shop_id":         shop_id,
            "user_id":         user_id,
            "title":           offer_data["title"],
            "description":     offer_data.get("description"),
            "discount_type":   offer_data["discount_type"],
            "discount_value":  float(offer_data["discount_value"]),
            "product_ids":     offer_data.get("product_ids", []),
            "category":        offer_data.get("category"),
            "target_segments": offer_data.get("target_segments", []),
            "valid_from":      valid_from,
            "valid_until":     valid_until,
            "is_active":       offer_data.get("is_active", True),
            "created_at":      now,
            "updated_at":      now,
        }
        await self.db.offers.insert_one(doc)
        doc.pop("_id", None)
        logger.info(f"Created offer {offer_id} for shop {shop_id}")
        return doc

    async def list_offers(
        self,
        shop_id: str,
        user_id: str,
        active_only: bool = True,
        segment: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List offers for a shop, optionally filtered to active or specific segment."""
        query: Dict[str, Any] = {"shop_id": shop_id, "user_id": user_id}
        if active_only:
            query["is_active"] = True
        if segment:
            query["target_segments"] = segment  # MongoDB treats as array contains

        offers = await self.db.offers.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
        return offers

    async def get_offer(self, offer_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single offer by its id."""
        return await self.db.offers.find_one({"id": offer_id}, {"_id": 0})

    async def update_offer(
        self,
        offer_id: str,
        user_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Patch-update an offer. Only provided fields are changed."""
        # Normalise date fields
        for date_field in ("valid_from", "valid_until"):
            if isinstance(updates.get(date_field), date):
                updates[date_field] = updates[date_field].isoformat()

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await self.db.offers.find_one_and_update(
            {"id": offer_id, "user_id": user_id},
            {"$set": updates},
            return_document=True,
            projection={"_id": 0},
        )
        return result

    async def delete_offer(self, offer_id: str, user_id: str) -> bool:
        """Soft-delete: set is_active=False instead of removing the document."""
        result = await self.db.offers.update_one(
            {"id": offer_id, "user_id": user_id},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return result.modified_count > 0

    async def get_offers_for_segment(
        self,
        shop_id: str,
        segment: str,
    ) -> List[Dict[str, Any]]:
        """Return all active offers that include the given segment in target_segments."""
        query = {
            "shop_id":         shop_id,
            "is_active":       True,
            "target_segments": segment,
        }
        return await self.db.offers.find(query, {"_id": 0}).to_list(200)

    # ═══════════════════════════════════════════════════════════════════════════
    # Composite Affinity Rank Engine
    # ═══════════════════════════════════════════════════════════════════════════

    def _affinity_score(
        self,
        insight: Dict[str, Any],
        offer: Dict[str, Any],
    ) -> float:
        """
        Compute Affinity(customer, offer) = S × (1 + P)

        S: segment validity (binary gate — offer must target the customer's segment)
        P: product/category preference score using w1 & w2 weights
        """
        customer_segment = (insight.get("segment") or "boring").lower()
        target_segments  = [s.lower() for s in offer.get("target_segments", [])]

        # ── Segment gate (S) ──────────────────────────────────────────────────
        if target_segments and customer_segment not in target_segments:
            return 0.0      # Offer not intended for this customer → drop

        # ── Product / Category Preference (P) ────────────────────────────────
        preference_score = 0.0
        offer_products   = {str(p).lower() for p in offer.get("product_ids", [])}
        offer_category   = (offer.get("category") or "").lower()

        # Customer product affinity fields from customer_insights
        customer_products = {
            str(insight.get("favorite_premium_product") or "").lower(),
            str(insight.get("favorite_bulk_product")    or "").lower(),
            str(insight.get("recently_bought_product")  or "").lower(),
        }
        customer_products.discard("")

        # I(product_match): any offer product overlaps with customer's fav/recent items
        if offer_products and customer_products & offer_products:
            preference_score += W_PRODUCT

        # I(category_match): offer category == customer's favourite category
        customer_fav_cat = (insight.get("favorite_category") or "").lower()
        if offer_category and customer_fav_cat and offer_category == customer_fav_cat:
            preference_score += W_CATEGORY

        affinity = 1.0 + preference_score
        return affinity  # S=1 implied here since we didn't return 0 above

    async def match_offers_to_customers(
        self,
        shop_id: str,
        user_id: str,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Run the affinity matching engine for all customers in the shop.

        Returns:
            {customer_id: best_offer_doc | None}

        Algorithm:
            1. Load all active offers for the shop.
            2. Load all customer_insights for the shop (pre-computed, indexed read).
            3. For each customer × offer: compute affinity score.
            4. Per customer: keep the highest-scoring offer (score > 0).
        """
        # ── Step 1: Active offers ─────────────────────────────────────────────
        active_offers = await self.db.offers.find(
            {"shop_id": shop_id, "is_active": True},
            {"_id": 0},
        ).to_list(500)

        if not active_offers:
            logger.info(f"No active offers for shop {shop_id}")
            return {}

        # ── Step 2: Customer insights (flat pre-computed cache) ───────────────
        insights_cursor = self.db.customer_insights.find(
            {"shop_id": shop_id}, {"_id": 0}
        )
        insights: List[Dict[str, Any]] = await insights_cursor.to_list(50000)

        if not insights:
            logger.info(f"No customer insights for shop {shop_id}")
            return {}

        # ── Step 3 & 4: Rank offers per customer ─────────────────────────────
        result: Dict[str, Optional[Dict[str, Any]]] = {}

        for insight in insights:
            customer_id = insight.get("customer_id")
            if not customer_id:
                continue

            best_offer  = None
            best_score  = 0.0

            for offer in active_offers:
                score = self._affinity_score(insight, offer)
                if score > best_score:
                    best_score = score
                    best_offer = offer

            result[customer_id] = best_offer  # None if no eligible offer found

        logger.info(
            f"Offer matching complete for shop {shop_id}: "
            f"{sum(1 for v in result.values() if v)} / {len(result)} customers matched"
        )
        return result

    async def get_match_preview(
        self,
        shop_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Return a human-readable preview of offer→customer matching results.
        Used by GET /api/shops/{shop_id}/offers/match endpoint.
        """
        match_map = await self.match_offers_to_customers(shop_id, user_id)

        # Aggregate: offer_id → list of matched customer_ids
        offer_customer_map: Dict[str, List[str]] = {}
        unmatched: List[str] = []

        for customer_id, offer in match_map.items():
            if offer:
                oid = offer["id"]
                offer_customer_map.setdefault(oid, []).append(customer_id)
            else:
                unmatched.append(customer_id)

        # Build summary list
        summaries = []
        for offer_id, cust_ids in offer_customer_map.items():
            # Find the offer doc
            offer_doc = next(
                (o for o in await self.db.offers.find(
                    {"id": offer_id}, {"_id": 0}
                ).to_list(1)),
                {}
            )
            summaries.append({
                "offer_id":        offer_id,
                "offer_title":     offer_doc.get("title", "Unknown"),
                "discount_type":   offer_doc.get("discount_type"),
                "discount_value":  offer_doc.get("discount_value"),
                "target_segments": offer_doc.get("target_segments", []),
                "matched_count":   len(cust_ids),
                "customer_ids":    cust_ids[:20],   # first 20 for preview
            })

        return {
            "total_customers": len(match_map),
            "matched_customers": len(match_map) - len(unmatched),
            "unmatched_customers": len(unmatched),
            "offer_matches": summaries,
        }
