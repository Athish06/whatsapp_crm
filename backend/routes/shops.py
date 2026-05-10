"""
Shop routes for shop management, file upload, and processing.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from typing import Any, Optional
from pydantic import BaseModel
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


class ProcessDataRequest(BaseModel):
    column_mapping: dict
    percentile: Optional[int] = 70


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
        shop = await service.create_shop(user_id, body.shop_name)
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
    """Required columns info for customer CSV."""
    return [
        {"key": "name", "label": "Customer Name", "description": "Full name of the customer"},
        {"key": "phone", "label": "Phone Number", "description": "Contact number (with country code)"},
        {"key": "purchase_count", "label": "Purchase Count (Frequency)", "description": "Total number of purchases — used for RFM Frequency quintile scoring"},
        {"key": "total_spent", "label": "Total Spent (Monetary)", "description": "Total amount spent — used for RFM Monetary quintile scoring"},
        {"key": "last_transaction_date", "label": "Last Purchase Date (Recency)", "description": "Date of last purchase (YYYY-MM-DD) — used for RFM Recency quintile scoring"},
        {"key": "quantity", "label": "Total Item Quantity", "description": "Total items ordered — used for Bulkiness factor"},
        {"key": "email", "label": "Email", "description": "Email address (optional)"},
    ]


def _suggest_mapping_for_type(data_type: str, columns: list) -> dict:
    """Auto-suggest column mapping based on data type and detected headers."""
    columns_lower = [c.lower() for c in columns]
    mapping = {}

    if data_type == "customers":
        field_keywords = {
            "name": ["name", "customer", "client", "full_name"],
            "phone": ["phone", "mobile", "contact", "tel", "cell"],
            "email": ["email", "mail", "e-mail"],
            "purchase_count": ["purchase_count", "orders", "purchase", "count", "visits", "transactions", "frequency"],
            "total_spent": ["total_spent", "total", "spent", "amount", "revenue", "spend", "monetary", "value"],
            "last_transaction_date": ["last_transaction_date", "last_date", "last_purchase", "date", "recent", "last_date_purchased"],
            "quantity": ["quantity", "qty", "items", "units", "total_qty", "total_quantity", "total_item_quantity"],
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
