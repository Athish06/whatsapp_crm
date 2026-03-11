"""
Batch routes for campaign management.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from schemas import BatchCreate, BatchSplitEstimate
from services import BatchService
from middleware import get_current_user
from config import get_db

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("/estimate", response_model=BatchSplitEstimate)
async def estimate_batch_split(
    total_customers: int = Query(..., description="Total number of customers"),
    batch_size: int = Query(100, description="Batch size")
):
    """Estimate batch splitting metrics."""
    result = BatchService.estimate_batch_split(total_customers, batch_size)
    return BatchSplitEstimate(**result)


@router.post("/create")
async def create_batch(
    batch_data: BatchCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Create a batch campaign.
    
    Supports two modes:
    1. Single template: Provide template_id - all customers get same template
    2. Segment-based: Provide segment_templates - different templates for different segments
    
    Campaign tracking: Provide campaign_name and file_id for campaign tracking in MongoDB
    """
    try:
        service = BatchService(db)
        user_id = current_user.get("user_id") or current_user.get("id")
        result = await service.create_batch(
            customer_ids=batch_data.customer_ids,
            batch_size=batch_data.batch_size,
            start_time=batch_data.start_time,
            priority=batch_data.priority,
            user_id=user_id,
            template_id=batch_data.template_id,
            segment_templates=batch_data.segment_templates,
            campaign_name=batch_data.campaign_name,
            file_id=batch_data.file_id
        )
        
        # Schedule batch processing in background
        background_tasks.add_task(
            service.process_pending_batches, 
            user_id
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
    user_id = current_user.get("user_id") or current_user.get("id")
    service = BatchService(db)
    batches = await service.list_batches(user_id)
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
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        await service.reschedule_batch(batch_id, user_id)
        
        # Restart processing
        background_tasks.add_task(
            service.process_pending_batches, 
            user_id
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


@router.delete("/clear-all")
async def clear_all_batches(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Clear all batches and messages for the current user."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        result = await service.clear_all_batches(user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/list")
async def list_campaigns(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """List all campaigns for the current user."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        campaigns = await db.campaigns.find(
            {"user_id": user_id}
        ).sort("created_at", -1).to_list(100)
        
        # Convert datetime and ObjectId to strings
        for campaign in campaigns:
            campaign["_id"] = str(campaign["_id"])
            if isinstance(campaign.get("created_at"), datetime):
                campaign["created_at"] = campaign["created_at"].isoformat()
            if isinstance(campaign.get("updated_at"), datetime):
                campaign["updated_at"] = campaign["updated_at"].isoformat()
        
        return {"campaigns": campaigns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/{campaign_id}")
async def get_campaign_details(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get detailed information about a campaign including its batches."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        
        # Get campaign
        campaign = await db.campaigns.find_one(
            {"_id": campaign_id, "user_id": user_id}
        )
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Get batches for this campaign
        batches = await db.batches.find(
            {"campaign_id": campaign_id},
            {"_id": 0}
        ).sort("batch_number", 1).to_list(1000)
        
        # Convert datetime fields
        if isinstance(campaign.get("created_at"), datetime):
            campaign["created_at"] = campaign["created_at"].isoformat()
        if isinstance(campaign.get("updated_at"), datetime):
            campaign["updated_at"] = campaign["updated_at"].isoformat()
        campaign["_id"] = str(campaign["_id"])
        
        return {
            "campaign": campaign,
            "batches": batches
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/stats")
async def get_queue_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get message queue statistics."""
    try:
        from services.scheduler_service import MessageQueueScheduler
        
        scheduler = MessageQueueScheduler(db)
        stats = await scheduler.get_queue_stats()
        
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
