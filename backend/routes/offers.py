"""
Offers routes — Phase 3

POST   /api/shops/{shop_id}/offers           — Create offer
GET    /api/shops/{shop_id}/offers           — List offers
GET    /api/shops/{shop_id}/offers/match     — Preview affinity match (must be before /{offer_id})
GET    /api/shops/{shop_id}/offers/{offer_id} — Get single offer
PUT    /api/shops/{shop_id}/offers/{offer_id} — Update offer
DELETE /api/shops/{shop_id}/offers/{offer_id} — Soft-delete offer
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from typing import Any, Optional

from config import Database
from middleware.auth import get_current_user
from services.offers_service import OffersService
from schemas.models import OfferCreate, OfferUpdate

router = APIRouter(prefix="/shops", tags=["offers"])


def _offers_service(db: Any = Depends(Database.get_database)) -> OffersService:
    return OffersService(db)


# ── Create ────────────────────────────────────────────────────────────────────
@router.post("/{shop_id}/offers")
async def create_offer(
    shop_id: str,
    body: OfferCreate,
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """Create a new offer for this shop."""
    user_id = current_user.get("user_id") or current_user.get("id")
    try:
        offer = await svc.create_offer(shop_id, user_id, body.model_dump())
        return offer
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── CSV Bulk Upload ───────────────────────────────────────────────────────────
@router.post("/{shop_id}/offers/upload-csv")
async def upload_offers_csv(
    shop_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """
    Bulk-create offers from a CSV file.
    
    Required columns: title, discount_type, discount_value
    Optional columns: description, offer_mode, product_ids, category,
                     target_segments, valid_from, valid_until
    
    product_ids and target_segments should be comma-separated within the cell.
    ALL product_ids must exist in the shop's product database or the entire
    file will be rejected.
    """
    user_id = current_user.get("user_id") or current_user.get("id")
    
    # Read and decode CSV
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to decode CSV file. Use UTF-8 encoding.")
    
    try:
        result = await svc.bulk_create_from_csv(shop_id, user_id, csv_text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV upload failed: {str(e)}")


# ── List ──────────────────────────────────────────────────────────────────────
@router.get("/{shop_id}/offers")
async def list_offers(
    shop_id: str,
    active_only: bool = Query(True),
    segment: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """List offers for a shop. Optionally filter by active_only or segment."""
    user_id = current_user.get("user_id") or current_user.get("id")
    offers = await svc.list_offers(shop_id, user_id, active_only=active_only, segment=segment)
    return {"offers": offers, "total": len(offers)}


# ── Match Preview (MUST be before /{offer_id} to avoid route collision) ───────
@router.get("/{shop_id}/offers/match")
async def preview_offer_match(
    shop_id: str,
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """
    Run the Composite Affinity Rank engine and return a preview of which
    customers are matched to which offers.
    """
    user_id = current_user.get("user_id") or current_user.get("id")
    try:
        preview = await svc.get_match_preview(shop_id, user_id)
        return preview
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get single ────────────────────────────────────────────────────────────────
@router.get("/{shop_id}/offers/{offer_id}")
async def get_offer(
    shop_id: str,
    offer_id: str,
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """Fetch a single offer by ID."""
    offer = await svc.get_offer(offer_id)
    if not offer or offer.get("shop_id") != shop_id:
        raise HTTPException(status_code=404, detail="Offer not found")
    return offer


# ── Update ────────────────────────────────────────────────────────────────────
@router.put("/{shop_id}/offers/{offer_id}")
async def update_offer(
    shop_id: str,
    offer_id: str,
    body: OfferUpdate,
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """Update an existing offer."""
    user_id = current_user.get("user_id") or current_user.get("id")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await svc.update_offer(offer_id, user_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Offer not found")
    return updated


# ── Soft-Delete ───────────────────────────────────────────────────────────────
@router.delete("/{shop_id}/offers/{offer_id}")
async def delete_offer(
    shop_id: str,
    offer_id: str,
    current_user: dict = Depends(get_current_user),
    svc: OffersService = Depends(_offers_service),
):
    """Soft-delete an offer (sets is_active=False, preserves history)."""
    user_id = current_user.get("user_id") or current_user.get("id")
    ok = await svc.delete_offer(offer_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Offer not found")
    return {"message": "Offer deactivated successfully"}
