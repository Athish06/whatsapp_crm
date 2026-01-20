"""
Customer routes.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import CustomerUploadResponse
from services import CustomerService
from services.file_service import file_service
from middleware import get_current_user
from config import get_db

router = APIRouter(prefix="/customers", tags=["customers"])


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
