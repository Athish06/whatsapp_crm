"""
Customer routes.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import CustomerUploadResponse
from services import CustomerService
from middleware import get_current_user
from config import get_db

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/upload", response_model=CustomerUploadResponse)
async def upload_customers(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Upload customers from CSV/Excel file."""
    try:
        content = await file.read()
        service = CustomerService(db)
        result = await service.upload_customers(
            content, 
            file.filename, 
            current_user["id"]
        )
        return CustomerUploadResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list")
async def list_customers(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """List all customers for the current user."""
    service = CustomerService(db)
    return await service.list_customers(current_user["id"])


@router.delete("/clear")
async def clear_customers(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Delete all customers for the current user."""
    service = CustomerService(db)
    deleted_count = await service.clear_customers(current_user["id"])
    return {"deleted_count": deleted_count}
