"""
Customer routes.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional
import json
from schemas import CustomerUploadResponse, ColumnDetectionResponse
from services import CustomerService
from services.file_service import file_service
from middleware import get_current_user
from config import get_db
from pydantic import BaseModel

router = APIRouter(prefix="/customers", tags=["customers"])


class ProcessFileRequest(BaseModel):
    column_mapping: dict
    percentile: Optional[int] = 70


@router.post("/process-file/{file_id}", response_model=CustomerUploadResponse)
async def process_uploaded_file(
    file_id: str,
    body: ProcessFileRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Process an already-uploaded B2 file by file_id with column mapping.
    Downloads the file from B2, classifies customers, and stores results.
    """
    try:
        from bson import ObjectId
        user_id = current_user.get("user_id") or current_user.get("id")

        # Fetch file metadata from DB
        file_doc = await db.files.find_one(
            {"_id": ObjectId(file_id), "user_id": user_id}
        )
        if not file_doc:
            raise HTTPException(status_code=404, detail="File not found")

        # Download file content from B2
        file_content = await file_service.download_file(file_doc["file_name"])

        # Process customers
        service = CustomerService(db)
        result = await service.upload_customers(
            file_content,
            file_doc["original_file_name"],
            user_id,
            file_url=file_doc.get("file_url"),
            file_id=str(file_doc["_id"]),
            column_mapping=body.column_mapping,
            percentile=body.percentile
        )

        return CustomerUploadResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


@router.post("/detect-columns", response_model=ColumnDetectionResponse)
async def detect_file_columns(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Detect columns in uploaded file and suggest mapping.
    
    This endpoint helps users map their CSV/PDF columns to required fields.
    Returns detected columns and suggested mappings.
    """
    try:
        # Validate file type
        allowed_extensions = {'.csv', '.xlsx', '.xls', '.pdf'}
        file_ext = '.' + file.filename.rsplit('.', 1)[-1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Read file content
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Detect columns
        service = CustomerService(db)
        result = await service.detect_file_columns(content, file.filename)
        
        return ColumnDetectionResponse(**result)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect columns: {str(e)}"
        )


@router.post("/upload-with-mapping", response_model=CustomerUploadResponse)
async def upload_customers_with_mapping(
    file: UploadFile = File(...),
    column_mapping: str = Form(...),
    percentile: Optional[int] = Form(70),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Upload customers with custom column mapping and dynamic segmentation.
    
    This endpoint uses PERCENTILE-BASED thresholds for segmentation:
    - Calculates 70th percentile (customizable) for purchase_count and avg_items_per_order
    - High Frequency + High Bulk = "both" (VIP)
    - High Frequency only = "frequent_customer"
    - High Bulk only = "bulk_buyer"
    - Low both = "regular"
    
    Args:
        file: CSV/PDF file
        column_mapping: JSON string mapping standard fields to CSV columns
            e.g., '{"name": "Customer_Full_Name", "phone": "Mobile_No"}'
        percentile: Percentile for dynamic thresholds (default 70)
    """
    try:
        # Parse column mapping
        mapping_dict = json.loads(column_mapping)
        
        # Validate file type
        allowed_extensions = {'.csv', '.xlsx', '.xls', '.pdf'}
        file_ext = '.' + file.filename.rsplit('.', 1)[-1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Get user_id
        user_id = current_user.get("user_id") or current_user.get("id")
        
        # Read file content
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Reset file position for file_service upload
        await file.seek(0)
        
        # Upload file to Blackblaze B2
        file_metadata = await file_service.upload_file(
            file=file,
            user_id=user_id,
            db=db
        )
        
        # Process customer data with dynamic segmentation
        service = CustomerService(db)
        result = await service.upload_customers(
            content,
            file.filename,
            user_id,
            file_url=file_metadata["file_url"],
            file_id=file_metadata["file_id"],
            column_mapping=mapping_dict,
            percentile=percentile
        )
        
        return CustomerUploadResponse(**result)
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid column_mapping JSON format")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process file: {str(e)}"
        )


@router.post("/upload", response_model=CustomerUploadResponse)
async def upload_customers(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Upload customers from CSV/Excel/PDF file.
    
    This endpoint:
    1. Uploads the file to Backblaze B2 cloud storage
    2. Stores file URL in 'files' collection with user_id
    3. Processes customer data and stores in 'customers' collection
    
    Supported formats: .csv, .xlsx, .xls, .pdf
    
    Required columns: name, phone
    Optional columns: email, total_quantity, purchase_count, order_value
    
    The system will automatically classify customers as:
    - Bulk Buyer: total_quantity >= 50 OR order_value >= 5000
    - Frequent Customer: purchase_count >= 10
    - Both: Meets both criteria
    - Regular: Others
    """
    try:
        # Validate file type
        allowed_extensions = {'.csv', '.xlsx', '.xls', '.pdf'}
        file_ext = '.' + file.filename.rsplit('.', 1)[-1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Get user_id from current_user
        user_id = current_user.get("user_id") or current_user.get("id")
        
        # Read file content once
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Reset file position for file_service upload
        await file.seek(0)
        
        # Step 1: Upload file to Backblaze B2 and store in 'files' collection
        file_metadata = await file_service.upload_file(
            file=file,
            user_id=user_id,
            db=db
        )
        
        # Step 2: Process customer data from file content
        service = CustomerService(db)
        result = await service.upload_customers(
            content, 
            file.filename, 
            user_id,
            file_url=file_metadata["file_url"],
            file_id=file_metadata["file_id"]
        )
        
        return CustomerUploadResponse(**result)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to process file: {str(e)}"
        )


@router.get("/list")
async def list_customers(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """List all customers for the current user."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = CustomerService(db)
    return await service.list_customers(user_id)


@router.get("/by-file/{file_id}")
async def get_customers_by_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get all customers associated with a specific file."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = CustomerService(db)
    return await service.get_customers_by_file(file_id, user_id)


@router.delete("/clear")
async def clear_customers(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Delete all customers for the current user."""
    user_id = current_user.get("user_id") or current_user.get("id")
    service = CustomerService(db)
    deleted_count = await service.clear_customers(user_id)
    return {"deleted_count": deleted_count}
