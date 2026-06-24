"""
Shop routes for shop management, file upload, and processing.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from typing import Any, Optional
from pydantic import BaseModel
from datetime import datetime
import logging

from config import Database
from middleware.auth import get_current_user
from services.shop_service import ShopService
from services.file_service import file_service
from services.customer_service import CustomerService
from services.product_service import ProductService
from services.transaction_service import TransactionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shops", tags=["shops"])


class CreateShopRequest(BaseModel):
    shop_name: str
    upload_cycle: Optional[str] = "monthly"


class ProcessDataRequest(BaseModel):
    column_mapping: dict
    percentile: Optional[int] = 70
    period_tag: Optional[str] = None


# ============ Shop CRUD ============

@router.post("/create")
async def create_shop(
    body: CreateShopRequest,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """Create a new shop."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = ShopService(db)
        shop = await service.create_shop(user_id, body.shop_name, body.upload_cycle)
        return shop
    except Exception as e:
        if "unique_user_shop_name" in str(e):
            raise HTTPException(status_code=400, detail="A shop with this name already exists")
        logger.error(f"Error creating shop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_shops(
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """List all shops with CSV status and live stats."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = ShopService(db)
    shops = await service.list_shops(user_id)
    return {"shops": shops}

@router.get("/{shop_id}/products")
async def list_shop_products(
    shop_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """List all products for a shop."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        products = await db.products.find({"shop_id": shop_id, "user_id": user_id}, {"_id": 0}).to_list(1000)
        return {"products": products}
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{shop_id}")
async def get_shop_detail(
    shop_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """Get full shop detail with CSV status, segmentation data, and behavioral insights."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = ShopService(db)
    shop = await service.get_shop_detail(shop_id, user_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.delete("/{shop_id}/campaign")
async def delete_campaign_data(
    shop_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """Delete only campaign data (messages, batches, campaigns) for a shop."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = ShopService(db)
    result = await service.delete_campaign_data(shop_id, user_id)
    return result


@router.delete("/{shop_id}")
async def delete_shop(
    shop_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """Permanently delete a shop and ALL associated data."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = ShopService(db)
    result = await service.delete_shop(shop_id, user_id)
    return result


# ============ Real Customer Preview ============

class PreviewRequest(BaseModel):
    template_text: str
    segment: Optional[str] = None
    customer_id: Optional[str] = None
    shop_id: Optional[str] = None


@router.post("/{shop_id}/preview-template")
async def preview_template(
    shop_id: str,
    body: PreviewRequest,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """Hydrate a template with real customer data for live preview.

    Uses customer_insights as the single source of truth for segments
    and all 8 template variables.
    """
    import re
    user_id = current_user.get("user_id") or current_user.get("id")

    # Build customer query — customers collection is identity-only, no segment stored.
    # Segment filtering is done via a join with customer_insights.
    cust_query = {"user_id": user_id, "shop_id": shop_id}

    if body.segment and body.segment not in ("all", ""):
        # Get customer_ids that belong to this segment from customer_insights
        seg_cursor = db.customer_insights.find(
            {"shop_id": shop_id, "segment": body.segment},
            {"_id": 0, "customer_id": 1}
        ).limit(20)
        seg_customer_ids = [doc["customer_id"] async for doc in seg_cursor]
        if not seg_customer_ids:
            return {
                "hydrated_text": body.template_text,
                "used_customer": None,
                "available_customers": [],
                "warning": f"No customers found for segment '{body.segment}'.",
            }
        cust_query["customer_id"] = {"$in": seg_customer_ids}

    # Fetch available customers (limit 10 for the toggle)
    available_cursor = db.customers.find(
        cust_query, {"_id": 0, "id": 1, "name": 1, "phone": 1, "customer_id": 1}
    ).limit(10)
    available_customers = [c async for c in available_cursor]

    if not available_customers:
        return {
            "hydrated_text": body.template_text,
            "used_customer": None,
            "available_customers": [],
            "warning": "No customers found for this segment.",
        }

    # Merge segment from customer_insights for UI compliance
    cust_keys = [c.get("customer_id") or c.get("phone", "") for c in available_customers]
    insights_cursor = db.customer_insights.find(
        {"shop_id": shop_id, "customer_id": {"$in": cust_keys}},
        {"customer_id": 1, "segment": 1}
    )
    insights_map = {doc["customer_id"]: doc.get("segment", "boring") async for doc in insights_cursor}
    for c in available_customers:
        key = c.get("customer_id") or c.get("phone", "")
        c["segment"] = insights_map.get(key, "boring")

    # Pick the requested customer or the first available with richest insight data
    chosen = None
    chosen_insight = {}

    if body.customer_id:
        # body.customer_id may be our internal UUID or the natural customer_id
        chosen_doc = await db.customers.find_one(
            {"$or": [{"id": body.customer_id}, {"customer_id": body.customer_id}],
             "user_id": user_id, "shop_id": shop_id},
            {"_id": 0},
        )
        if chosen_doc:
            chosen = chosen_doc

    if not chosen:
        # Pick the first customer that has behavioral insight data (richest preview)
        for ac in available_customers:
            cust_key = ac.get("customer_id") or ac.get("phone", "")
            insight = await db.customer_insights.find_one(
                {"shop_id": shop_id, "customer_id": cust_key}, {"_id": 0}
            )
            if insight and insight.get("favorite_category"):
                chosen = await db.customers.find_one(
                    {"customer_id": cust_key, "shop_id": shop_id, "user_id": user_id},
                    {"_id": 0},
                )
                chosen_insight = insight
                break
        if not chosen:
            chosen = await db.customers.find_one(
                {"customer_id": available_customers[0].get("customer_id"),
                 "shop_id": shop_id, "user_id": user_id},
                {"_id": 0},
            ) or {}

    # Fetch insight data for this customer from customer_insights (single source of truth)
    if not chosen_insight:
        cust_id_for_insight = chosen.get("customer_id") or chosen.get("phone", "")
        chosen_insight = await db.customer_insights.find_one(
            {"shop_id": shop_id, "customer_id": cust_id_for_insight}, {"_id": 0}
        ) or {}

    # Match offer for preview customer
    offer_title = "Great deals throughout our store"
    offer_discount_str = "the best wholesale prices"
    offer_product_str = "your next household purchase"

    try:
        from services.offers_service import OffersService
        offers_svc = OffersService(db)
        cust_key = chosen.get("customer_id") or chosen.get("phone", "")
        offer_match_map = await offers_svc.match_offers_to_customers(shop_id, user_id)
        best_offer = offer_match_map.get(cust_key) or {}
        if best_offer:
            offer_title = best_offer.get("title", "") or "Great deals throughout our store"
            offer_discount_type  = best_offer.get("discount_type", "")
            offer_discount_value = best_offer.get("discount_value", "")
            if offer_discount_type == "percentage":
                offer_discount_str = f"{offer_discount_value}% OFF"
            elif offer_discount_type == "flat":
                offer_discount_str = f"₹{offer_discount_value} OFF"
            elif offer_discount_type == "bogo":
                offer_discount_str = "Buy 1 Get 1 Free"
            else:
                offer_discount_str = str(offer_discount_value) if offer_discount_value else "the best wholesale prices"
            
            product_ids = best_offer.get("product_ids", [])
            offer_product_str = ", ".join(str(p) for p in product_ids) if product_ids else "your next household purchase"
    except Exception as _offer_err:
        logger.warning(f"Preview offer matching skipped: {_offer_err}")

    # Build replacement map — the 11 smart variables
    replacements = {
        "customer_name": chosen.get("name", ""),
        "segment": chosen_insight.get("segment", ""),
        "favorite_category": chosen_insight.get("favorite_category", ""),
        "favorite_premium_product": chosen_insight.get("favorite_premium_product", ""),
        "favorite_bulk_product": chosen_insight.get("favorite_bulk_product", ""),
        "second_favorite_premium_product": chosen_insight.get("second_favorite_premium_product", ""),
        "recently_bought_product": chosen_insight.get("recently_bought_product", ""),
        "complementary_product": chosen_insight.get("complementary_product", ""),
        "offer_title": offer_title,
        "offer_discount": offer_discount_str,
        "offer_product": offer_product_str,
    }


    # Hydrate
    hydrated = body.template_text
    for key, val in replacements.items():
        hydrated = hydrated.replace("{{" + key + "}}", str(val or ""))

    # Check for unresolved variables
    unresolved = re.findall(r"\{\{(\w+)\}\}", hydrated)

    return {
        "hydrated_text": hydrated,
        "used_customer": {
            "customer_id": chosen.get("customer_id") or chosen.get("id"),
            "customer_name": chosen.get("name"),
            "segment": chosen_insight.get("segment", ""),
        },
        "available_customers": [
            {
                "id": c.get("id") or c.get("customer_id"),
                "name": c.get("name", ""),
                "segment": c.get("segment", ""),  # kept for UI compat
            }
            for c in available_customers
        ],
        "replacements_applied": replacements,
        "unresolved_variables": unresolved,
        "warning": "Some variables could not be filled — customer may lack transaction data." if unresolved else None,
    }


# ============ Resend Failed / Unsent ============

class ResendRequest(BaseModel):
    mode: str = "failed"  # "failed" | "unsent" | "all"


@router.post("/{shop_id}/campaigns/{campaign_id}/resend")
async def resend_campaign_messages(
    shop_id: str,
    campaign_id: str,
    body: ResendRequest,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """Re-queue failed / unsent / all messages for a campaign.

    Max 2 retries per message. After that, messages move to dead_letter status.
    """
    from datetime import timedelta
    from services import BatchService

    user_id = current_user.get("user_id") or current_user.get("id")

    # Get batch IDs for this campaign
    batch_ids = [
        b["id"] async for b in db.batches.find(
            {"campaign_id": campaign_id, "user_id": user_id}, {"_id": 0, "id": 1}
        )
    ]
    if not batch_ids:
        raise HTTPException(status_code=404, detail="No batches found for this campaign")

    # Determine which statuses to re-queue
    if body.mode == "failed":
        target_statuses = ["failed"]
    elif body.mode == "unsent":
        target_statuses = ["cancelled", "unsent"]
    else:
        target_statuses = ["failed", "cancelled", "unsent"]

    # Find eligible messages (retry_count < 2)
    messages = await db.messages.find(
        {
            "batch_id": {"$in": batch_ids},
            "status": {"$in": target_statuses},
            "retry_count": {"$lt": 2},
        },
        {"_id": 0},
    ).to_list(10000)

    if not messages:
        # Check if any are past max retries
        dead_count = await db.messages.count_documents(
            {"batch_id": {"$in": batch_ids}, "status": {"$in": target_statuses}, "retry_count": {"$gte": 2}}
        )
        return {
            "message": "No messages eligible for resend.",
            "requeued": 0,
            "dead_letter": dead_count,
        }

    now = datetime.now()
    requeued = 0
    dead = 0

    for msg in messages:
        retry = msg.get("retry_count", 0) + 1
        if retry > 2:
            # Move to dead_letter
            await db.messages.update_one(
                {"id": msg["id"]},
                {"$set": {"status": "dead_letter", "retry_count": retry}},
            )
            dead += 1
            continue

        # Re-queue
        scheduled = now + timedelta(minutes=5)
        await db.messages.update_one(
            {"id": msg["id"]},
            {"$set": {"status": "pending", "retry_count": retry, "scheduled_at": scheduled, "error": None}},
        )
        # Also re-create queue item
        await db.msg_queues.update_one(
            {"message_id": msg["id"]},
            {
                "$set": {
                    "status": "pending",
                    "scheduled_at": scheduled,
                    "updated_at": now.isoformat(),
                },
                "$setOnInsert": {
                    "id": msg["id"],
                    "message_id": msg["id"],
                    "user_id": user_id,
                    "campaign_id": campaign_id,
                    "batch_id": msg["batch_id"],
                    "customer_id": msg.get("customer_id"),
                    "phone_number": msg.get("phone_number"),
                    "customer_segment": msg.get("customer_segment", "boring"),
                    "priority": msg.get("priority", 4),
                    "created_at": now.isoformat(),
                },
            },
            upsert=True,
        )
        requeued += 1

    # Reset the parent batches that contained failed messages back to pending
    if requeued > 0:
        affected_batch_ids = list({m["batch_id"] for m in messages})
        await db.batches.update_many(
            {"id": {"$in": affected_batch_ids}, "status": {"$in": ["failed", "completed", "cancelled"]}},
            {"$set": {"status": "pending"}},
        )
        await db.campaigns.update_one(
            {"_id": campaign_id},
            {"$set": {"status": "pending", "updated_at": now}},
        )

    return {
        "message": f"Re-queued {requeued} messages. {dead} moved to dead letter (max retries).",
        "requeued": requeued,
        "dead_letter": dead,
    }


# ============ Unified Upload & Process ============

@router.post("/{shop_id}/upload/{data_type}")
async def upload_shop_file(
    shop_id: str,
    data_type: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """
    Upload a CSV file for a shop.
    data_type must be one of: customers, products, transactions

    Returns file_id + detected columns + suggested mapping.
    """
    valid_types = {"customers": "customer_data", "products": "product_data", "transactions": "transaction_data"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data_type. Must be one of: {', '.join(valid_types.keys())}")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    user_id = current_user.get("user_id") or current_user.get("id")

    try:
        # Upload to B2
        result = await file_service.upload_file(
            file=file,
            user_id=user_id,
            db=db,
            shop_id=shop_id,
            data_purpose=valid_types[data_type],
        )

        file_id = result["file_id"]

        # Detect columns
        from bson import ObjectId
        file_doc = await db.files.find_one({"_id": ObjectId(file_id)})
        file_content = await file_service.download_file(file_doc["file_name"])

        # Get columns and suggested mapping
        customer_service = CustomerService(db)
        col_result = await customer_service.detect_file_columns(file_content, file_doc["original_file_name"])

        # Build type-specific suggested mapping
        detected_columns = col_result["columns"]
        suggested_mapping = _suggest_mapping_for_type(data_type, detected_columns)

        # Get required columns info
        if data_type == "customers":
            required_info = _get_customer_required_columns()
        elif data_type == "products":
            required_info = ProductService.get_required_columns()
        else:
            required_info = TransactionService.get_required_columns()

        return {
            "file_id": file_id,
            "file_name": result["file_name"],
            "duplicate": result.get("duplicate", False),
            "detected_columns": detected_columns,
            "suggested_mapping": suggested_mapping,
            "required_columns": required_info,
            "data_type": data_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading {data_type} file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{shop_id}/process/{data_type}/{file_id}")
async def process_shop_file(
    shop_id: str,
    data_type: str,
    file_id: str,
    body: ProcessDataRequest,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(Database.get_database),
):
    """
    Process an uploaded file with the user's column mapping.
    data_type must be one of: customers, products, transactions
    """
    valid_types = {"customers", "products", "transactions"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data_type. Must be one of: {', '.join(valid_types)}")

    user_id = current_user.get("user_id") or current_user.get("id")

    try:
        from bson import ObjectId

        # Fetch file
        file_doc = await db.files.find_one({"_id": ObjectId(file_id), "user_id": user_id})
        if not file_doc:
            raise HTTPException(status_code=404, detail="File not found")

        # Download content
        file_content = await file_service.download_file(file_doc["file_name"])

        if data_type == "customers":
            service = CustomerService(db)
            result = await service.upload_customers(
                file_content,
                file_doc["original_file_name"],
                user_id,
                shop_id=shop_id,
                file_url=file_doc.get("file_url"),
                file_id=str(file_doc["_id"]),
                campaign_id=file_doc.get("campaign_id"),
                column_mapping=body.column_mapping,
                percentile=body.percentile,
                period_tag=body.period_tag or file_doc.get("period_tag"),
            )
            return result

        elif data_type == "products":
            service = ProductService(db)
            result = await service.process_products(
                file_content,
                file_doc["original_file_name"],
                user_id,
                shop_id,
                body.column_mapping,
            )
            return result

        elif data_type == "transactions":
            service = TransactionService(db)
            result = await service.process_transactions(
                file_content,
                file_doc["original_file_name"],
                user_id,
                shop_id,
                body.column_mapping,
                period_tag=body.period_tag or file_doc.get("period_tag"),
            )
            return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing {data_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Helpers ============

def _get_customer_required_columns():
    """Required columns info for customer CSV.
    
    In the 3-layer architecture, customer CSV only needs basic bio data.
    RFM metrics are computed from transactions automatically.
    """
    return [
        {"key": "customer_id", "label": "Customer ID", "description": "Unique customer identifier — links to Transaction file"},
        {"key": "name", "label": "Customer Name", "description": "Full name of the customer"},
        {"key": "phone", "label": "Phone / Mobile No", "description": "Contact number (with country code)"},
    ]


def _suggest_mapping_for_type(data_type: str, columns: list) -> dict:
    """Auto-suggest column mapping based on data type and detected headers."""
    columns_lower = [c.lower() for c in columns]
    mapping = {}

    if data_type == "customers":
        field_keywords = {
            "customer_id": ["customer_id", "cust_id", "id", "customer_no", "customer_code"],
            "name": ["name", "customer_name", "customer", "client", "full_name"],
            "phone": ["phone", "mobile", "mobile_no", "contact", "tel", "cell"],
        }
    elif data_type == "products":
        field_keywords = {
            "product_id": ["product_id", "id", "sku", "item_id", "code", "product_code"],
            "product_name": ["product_name", "name", "item", "product", "description", "item_name"],
            "category": ["category", "cat", "type", "group", "department", "section"],
            "price": ["price", "cost", "mrp", "rate", "amount", "unit_price"],
            "unit": ["unit", "uom", "measure", "pack_size", "size", "weight"],
        }
    elif data_type == "transactions":
        field_keywords = {
            "customer_id": ["customer_id", "customer", "phone", "mobile", "cust_id", "buyer"],
            "product_id": ["product_id", "product", "item_id", "sku", "item", "product_code"],
            "purchase_date": ["purchase_date", "date", "order_date", "transaction_date", "invoice_date", "bought_on"],
            "quantity": ["quantity", "qty", "units", "count", "items"],
            "amount": ["amount", "total", "price", "value", "spend", "cost", "total_amount"],
        }
    else:
        return {}

    for field, keywords in field_keywords.items():
        mapping[field] = None
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in keywords):
                mapping[field] = col
                break

    return mapping
