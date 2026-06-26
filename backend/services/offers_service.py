"""
Offers Service — Phase 3 (Overhauled)

Provides full offer lifecycle management, CSV bulk import with strict product
validation, and the 6-Phase Waterfall Offer Matching Engine.

6-Phase Waterfall:
    Phase 1: General offers matched by customer's top_n_product_ids
    Phase 2: General offers matched by customer's favorite_category
    Phase 3: General offers matched by customer's favorite_premium_product_id
    Phase 4: General offers matched by customer's favorite_bulk_product_id
    Phase 5: Segment-tagged offers → direct map to customer's segment
    Phase 6: Upsell offers (optional) → offers from the next-tier-up segment
"""
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional, Set, Tuple
import uuid
import csv
import io
import logging

logger = logging.getLogger(__name__)

# ── Upsell segment hierarchy ─────────────────────────────────────────────────
UPSELL_MAP = {
    "boring":          ["loyal_frequent"],
    "at_risk":         ["loyal_frequent"],
    "loyal_frequent":  ["vip"],
    "potential_bulk":  ["potential_bulk", "vip"],  # Bulk+VIP hybrid
}

# ── Offer list cap per customer message ───────────────────────────────────────
MAX_OFFERS_PER_CUSTOMER = 5

# ── Required CSV columns ─────────────────────────────────────────────────────
REQUIRED_CSV_COLS = {"title", "discount_type", "discount_value"}


class OffersService:
    """Service for offer lifecycle, CSV import, and 6-phase waterfall matching."""

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
            "offer_mode":      offer_data.get("offer_mode", "individual"),
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
    # CSV Bulk Upload
    # ═══════════════════════════════════════════════════════════════════════════

    async def bulk_create_from_csv(
        self,
        shop_id: str,
        user_id: str,
        csv_content: str,
    ) -> Dict[str, Any]:
        """
        Parse a CSV string and create offers in bulk.

        Strict validation:
          - All required columns must be present
          - Every product_id in the CSV must exist in the shop's products collection
          - If ANY product_id is invalid, the ENTIRE file is rejected

        Returns:
            {"created": N, "offers": [...]} on success
            Raises ValueError with detailed message on failure
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        # Normalise header names (strip whitespace, lowercase)
        headers = {h.strip().lower() for h in reader.fieldnames}

        # Check required columns
        missing = REQUIRED_CSV_COLS - headers
        if missing:
            raise ValueError(
                f"Missing required columns: {', '.join(sorted(missing))}. "
                f"Required: {', '.join(sorted(REQUIRED_CSV_COLS))}"
            )

        # Parse all rows first (don't insert anything yet)
        rows = []
        all_product_ids: Set[str] = set()
        for i, row in enumerate(reader, start=2):  # start=2 because row 1 is headers
            # Normalise keys
            row = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

            if not row.get("title"):
                raise ValueError(f"Row {i}: 'title' is required")
            if not row.get("discount_value"):
                raise ValueError(f"Row {i}: 'discount_value' is required")

            # Parse product_ids (comma-separated)
            raw_pids = row.get("product_ids", "")
            product_ids = [p.strip() for p in raw_pids.split(",") if p.strip()] if raw_pids else []
            all_product_ids.update(product_ids)

            # Parse target_segments (comma-separated, optional)
            raw_segs = row.get("target_segments", "")
            target_segments = [s.strip() for s in raw_segs.split(",") if s.strip()] if raw_segs else []

            rows.append({
                "title": row["title"],
                "description": row.get("description", ""),
                "discount_type": row.get("discount_type", "percentage"),
                "discount_value": row["discount_value"],
                "offer_mode": row.get("offer_mode", "individual"),
                "product_ids": product_ids,
                "category": row.get("category", "") or None,
                "target_segments": target_segments,
                "valid_from": row.get("valid_from") or None,
                "valid_until": row.get("valid_until") or None,
            })

        if not rows:
            raise ValueError("CSV file contains no data rows")

        # ── Validate ALL product_ids against the shop's products collection ──
        if all_product_ids:
            existing_products = await self.db.products.find(
                {"shop_id": shop_id, "product_id": {"$in": list(all_product_ids)}},
                {"product_id": 1}
            ).to_list(5000)
            existing_pids = {p["product_id"] for p in existing_products}
            invalid_pids = all_product_ids - existing_pids

            if invalid_pids:
                raise ValueError(
                    f"Invalid product IDs not found in database: {', '.join(sorted(invalid_pids))}. "
                    f"Fix these product IDs and re-upload the CSV."
                )

        # ── All valid — bulk insert ──
        created_offers = []
        for row_data in rows:
            offer = await self.create_offer(shop_id, user_id, row_data)
            created_offers.append(offer)

        logger.info(f"CSV bulk import: created {len(created_offers)} offers for shop {shop_id}")
        return {"created": len(created_offers), "offers": created_offers}

    # ═══════════════════════════════════════════════════════════════════════════
    # 6-Phase Waterfall Offer Matching Engine
    # ═══════════════════════════════════════════════════════════════════════════

    async def match_offers_to_customers(
        self,
        shop_id: str,
        user_id: str,
        enable_upsell: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run the 6-phase waterfall matching engine for all customers in the shop.

        Returns:
            {customer_id: [list of matched offer docs]} — capped at MAX_OFFERS_PER_CUSTOMER

        Phases (strict order):
            1. General offers matched by customer's top_n_product_ids
            2. General offers matched by customer's favorite_category
            3. General offers matched by customer's favorite_premium_product_id
            4. General offers matched by customer's favorite_bulk_product_id (optional)
            5. Segment-tagged offers → direct map to customer's segment
            6. Upsell offers (only if enable_upsell=True) → next-tier-up segment
        """
        # ── Load active offers ────────────────────────────────────────────────
        active_offers = await self.db.offers.find(
            {"shop_id": shop_id, "is_active": True},
            {"_id": 0},
        ).to_list(500)

        if not active_offers:
            logger.info(f"No active offers for shop {shop_id}")
            return {}

        # ── Pre-split offers into general vs segment-tagged ───────────────────
        general_offers = []
        segment_offers = []  # offers with at least one target_segment
        for offer in active_offers:
            if offer.get("target_segments"):
                segment_offers.append(offer)
            else:
                general_offers.append(offer)

        # ── Build product_id → category lookup map ────────────────────────────
        all_products = await self.db.products.find(
            {"shop_id": shop_id},
            {"_id": 0, "product_id": 1, "category": 1, "product_name": 1},
        ).to_list(5000)
        prod_category_map = {p["product_id"]: p.get("category", "") for p in all_products}
        prod_name_map = {p["product_id"]: p.get("product_name", p["product_id"]) for p in all_products}

        # ── Load customer insights ────────────────────────────────────────────
        insights_cursor = self.db.customer_insights.find(
            {"shop_id": shop_id}, {"_id": 0}
        )
        insights: List[Dict[str, Any]] = await insights_cursor.to_list(50000)

        if not insights:
            logger.info(f"No customer insights for shop {shop_id}")
            return {}

        # ── Run 6-phase waterfall for each customer ───────────────────────────
        result: Dict[str, List[Dict[str, Any]]] = {}

        for insight in insights:
            customer_id = insight.get("customer_id")
            if not customer_id:
                continue

            matched: List[Dict[str, Any]] = []
            matched_ids: Set[str] = set()  # dedup tracker

            customer_segment = (insight.get("segment") or "boring").lower()
            top_n_pids = set(insight.get("top_n_product_ids", []))
            fav_category = (insight.get("favorite_category") or "").lower()
            prem_pid = insight.get("favorite_premium_product_id")
            bulk_pid = insight.get("favorite_bulk_product_id")

            def _add_offer(offer: Dict[str, Any]):
                """Add offer if not already matched, respecting cap."""
                oid = offer["id"]
                if oid not in matched_ids and len(matched) < MAX_OFFERS_PER_CUSTOMER:
                    matched_ids.add(oid)
                    matched.append(offer)

            # ── Phase 1: Top N Product Match (General Only) ───────────────
            for offer in general_offers:
                offer_pids = set(offer.get("product_ids", []))
                if offer_pids and top_n_pids & offer_pids:
                    # For combined offers: even 1 match is enough for general
                    _add_offer(offer)

            # ── Phase 2: Favorite Category Match (General Only) ───────────
            if fav_category:
                for offer in general_offers:
                    offer_pids = offer.get("product_ids", [])
                    # Check offer's explicit category field first
                    offer_cat = (offer.get("category") or "").lower()
                    if offer_cat and offer_cat == fav_category:
                        _add_offer(offer)
                        continue
                    # Fallback: check if any of the offer's products are in the fav category
                    if offer_pids:
                        offer_cats = {prod_category_map.get(pid, "").lower() for pid in offer_pids}
                        if fav_category in offer_cats:
                            _add_offer(offer)

            # ── Phase 3: Favorite Premium Product Match (General Only) ────
            if prem_pid:
                for offer in general_offers:
                    offer_pids = set(offer.get("product_ids", []))
                    if prem_pid in offer_pids:
                        _add_offer(offer)

            # ── Phase 4: Favorite Bulk Product Match (General Only) ───────
            if bulk_pid:
                for offer in general_offers:
                    offer_pids = set(offer.get("product_ids", []))
                    if bulk_pid in offer_pids:
                        _add_offer(offer)

            # ── Phase 5: Segment Direct Map ───────────────────────────────
            for offer in segment_offers:
                target_segs = [s.lower() for s in offer.get("target_segments", [])]
                if customer_segment in target_segs:
                    _add_offer(offer)

            # ── Phase 6: Upsell (Optional) ────────────────────────────────
            if enable_upsell:
                upsell_targets = UPSELL_MAP.get(customer_segment, [])
                if upsell_targets:
                    for offer in segment_offers:
                        target_segs = [s.lower() for s in offer.get("target_segments", [])]
                        if any(ut in target_segs for ut in upsell_targets):
                            _add_offer(offer)

            result[customer_id] = matched

        # ── Stats ─────────────────────────────────────────────────────────────
        matched_count = sum(1 for v in result.values() if v)
        total_offers_assigned = sum(len(v) for v in result.values())
        logger.info(
            f"Offer matching complete for shop {shop_id}: "
            f"{matched_count}/{len(result)} customers matched, "
            f"{total_offers_assigned} total offer assignments"
        )
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # Offer List Formatter (for {{offer_list}} template variable)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def format_offer_list(
        offers: List[Dict[str, Any]],
        prod_name_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Format a list of matched offers into a WhatsApp-friendly text block.

        Individual: 🏷️ 20% off Rice 5kg
        Combined:   🏷️ Buy Rice + Oil + Soap combo at 30% off
        """
        if not offers:
            return ""

        lines = []
        for offer in offers:
            discount = offer.get("discount_value", 0)
            d_type = offer.get("discount_type", "percentage")
            mode = offer.get("offer_mode", "individual")
            product_ids = offer.get("product_ids", [])

            # Resolve product names
            if prod_name_map and product_ids:
                product_names = [prod_name_map.get(pid, pid) for pid in product_ids]
            else:
                product_names = product_ids if product_ids else [offer.get("title", "items")]

            # Format discount string
            if d_type == "percentage":
                discount_str = f"{discount}% off"
            elif d_type == "flat":
                discount_str = f"₹{discount} off"
            elif d_type == "bogo":
                discount_str = "Buy 1 Get 1 Free on"
            else:
                discount_str = f"{discount} off"

            if mode == "combined" and len(product_names) > 1:
                products_str = " + ".join(product_names[:4])
                if len(product_names) > 4:
                    products_str += f" + {len(product_names) - 4} more"
                lines.append(f"🏷️ Buy {products_str} combo at {discount_str}")
            else:
                # Individual: one line per product (but cap to avoid bloat)
                for pname in product_names[:3]:
                    lines.append(f"🏷️ {discount_str} {pname}")
                if len(product_names) > 3:
                    lines.append(f"   ...and {len(product_names) - 3} more products")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════════
    # Match Preview (API endpoint helper)
    # ═══════════════════════════════════════════════════════════════════════════

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

        for customer_id, offers in match_map.items():
            if offers:
                for offer in offers:
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
                "offer_mode":      offer_doc.get("offer_mode", "individual"),
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
