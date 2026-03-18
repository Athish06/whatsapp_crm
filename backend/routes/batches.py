"""
Batch routes for campaign management.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from schemas import BatchCreate, BatchSplitEstimate, BatchUpdateRequest
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


@router.get("/file/{file_id}/summary")
async def get_file_schedule_summary(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get scheduling summary for a specific uploaded file."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        campaigns = await db.campaigns.find(
            {"user_id": user_id, "file_id": file_id},
            {"_id": 0, "campaign_name": 1, "created_at": 1, "status": 1}
        ).sort("created_at", -1).to_list(100)

        batches = await db.batches.find(
            {"user_id": user_id, "file_id": file_id},
            {"_id": 0, "id": 1, "status": 1, "success_count": 1, "failed_count": 1, "customer_count": 1, "created_at": 1}
        ).to_list(5000)

        batch_ids = [b.get("id") for b in batches if b.get("id")]
        if batch_ids:
            sent_messages = await db.messages.count_documents(
                {"user_id": user_id, "batch_id": {"$in": batch_ids}, "status": {"$in": ["sent", "delivered"]}}
            )
            failed_messages = await db.messages.count_documents(
                {"user_id": user_id, "batch_id": {"$in": batch_ids}, "status": {"$in": ["failed", "failed_permanently"]}}
            )
        else:
            sent_messages = 0
            failed_messages = 0

        return {
            "file_id": file_id,
            "schedule_count": len(campaigns),
            "total_batches": len(batches),
            "active_batches": sum(1 for b in batches if b.get("status") in ["pending", "scheduled", "sending"]),
            "messages_sent": sent_messages,
            "messages_failed": failed_messages,
            "last_scheduled_at": campaigns[0].get("created_at") if campaigns else None,
            "campaigns": campaigns,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.patch("/{batch_id}")
async def update_batch(
    batch_id: str,
    payload: BatchUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Edit scheduled batch time/templates before it is completed."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        result = await service.update_batch(
            batch_id=batch_id,
            user_id=user_id,
            start_time=payload.start_time,
            template_id=payload.template_id,
            segment_templates=payload.segment_templates,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{batch_id}/pause")
async def pause_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Pause a scheduled batch."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        return await service.pause_batch(batch_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{batch_id}/resume")
async def resume_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Resume a paused batch."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        result = await service.resume_batch(batch_id, user_id)
        background_tasks.add_task(service.process_pending_batches, user_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{batch_id}")
async def delete_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Delete extra/wrongly created scheduled batch."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        return await service.delete_batch(batch_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
