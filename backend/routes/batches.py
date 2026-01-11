"""
Batch routes for campaign management.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import BatchCreate, BatchSplitEstimate
from services import BatchService
from middleware import get_current_user
from config import get_db

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("/estimate", response_model=BatchSplitEstimate)
async def estimate_batch_split(request: dict):
    """Estimate batch splitting metrics."""
    total_customers = request.get("total_customers", 0)
    batch_size = request.get("batch_size", 100)
    result = BatchService.estimate_batch_split(total_customers, batch_size)
    return BatchSplitEstimate(**result)


@router.post("/create")
async def create_batch(
    batch_data: BatchCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Create a batch campaign."""
    try:
        service = BatchService(db)
        result = await service.create_batch(
            template_id=batch_data.template_id,
            customer_ids=batch_data.customer_ids,
            batch_size=batch_data.batch_size,
            start_time=batch_data.start_time,
            priority=batch_data.priority,
            user_id=current_user["id"]
        )
        
        # Schedule batch processing in background
        background_tasks.add_task(
            service.process_pending_batches, 
            current_user["id"]
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/list")
async def list_batches(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """List all batches for the current user."""
    service = BatchService(db)
    batches = await service.list_batches(current_user["id"])
    return {"batches": batches}


@router.post("/{batch_id}/reschedule")
async def reschedule_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Reschedule a failed batch."""
    try:
        service = BatchService(db)
        await service.reschedule_batch(batch_id, current_user["id"])
        
        # Restart processing
        background_tasks.add_task(
            service.process_pending_batches, 
            current_user["id"]
        )
        
        return {"message": "Batch rescheduled successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{batch_id}/messages")
async def get_batch_messages(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get all messages for a batch."""
    service = BatchService(db)
    messages = await service.get_batch_messages(batch_id)
    return {"messages": messages}
