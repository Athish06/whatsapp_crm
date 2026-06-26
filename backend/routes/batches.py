"""
Batch routes for campaign management.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Any
from datetime import datetime, timezone
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
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
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
            file_id=batch_data.file_id,
            shop_id=batch_data.shop_id,
            ai_mode=batch_data.ai_mode if hasattr(batch_data, 'ai_mode') else False,
            fixed_product=batch_data.fixed_product if hasattr(batch_data, 'fixed_product') else None,
        )
        
        # The scheduler worker (7s poll) will automatically pick up
        # the newly enqueued items — no manual trigger needed.
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/list")
async def list_batches(
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
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
    db: Any = Depends(get_db)
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

        queue_pending = await db.messages.count_documents({"user_id": user_id, "batch_id": {"$in": [b.get("id") for b in batches if b.get("id")]}, "status": "pending"}) if batches else 0

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
            "messages_in_queue": queue_pending,
            "last_scheduled_at": campaigns[0].get("created_at") if campaigns else None,
            "campaigns": campaigns,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{batch_id}/reschedule")
async def reschedule_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
):
    """Reschedule a failed batch. Scheduler worker picks up items automatically."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        await service.reschedule_batch(batch_id, user_id)
        return {"message": "Batch rescheduled successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{batch_id}")
async def update_batch(
    batch_id: str,
    payload: BatchUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
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
    db: Any = Depends(get_db)
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
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
):
    """Resume a paused batch. Scheduler worker picks up items automatically."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        result = await service.resume_batch(batch_id, user_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{batch_id}")
async def delete_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
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
    db: Any = Depends(get_db)
):
    """Get all messages for a batch."""
    service = BatchService(db)
    messages = await service.get_batch_messages(batch_id)
    return {"messages": messages}


@router.delete("/clear-all")
async def clear_all_batches(
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
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
    db: Any = Depends(get_db),
):
    """List all campaigns with live stats (sent, failed, segment breakdown)."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        campaigns = await db.campaigns.find(
            {"user_id": user_id}
        ).sort("created_at", -1).to_list(100)

        result = []
        for c in campaigns:
            c["_id"] = str(c["_id"])
            if isinstance(c.get("created_at"), datetime):
                dt = c["created_at"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                c["created_at"] = dt.isoformat()
            if isinstance(c.get("updated_at"), datetime):
                dt = c["updated_at"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                c["updated_at"] = dt.isoformat()
            if isinstance(c.get("completed_at"), datetime):
                dt = c["completed_at"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                c["completed_at"] = dt.isoformat()

            # Live message counts straight from messages collection
            campaign_id = c["_id"]
            batch_ids_cursor = db.batches.find(
                {"campaign_id": campaign_id}, {"_id": 0, "id": 1}
            )
            batch_ids = [b["id"] async for b in batch_ids_cursor]

            if batch_ids:
                sent = await db.messages.count_documents(
                    {"batch_id": {"$in": batch_ids}, "status": {"$in": ["sent", "delivered"]}}
                )
                failed = await db.messages.count_documents(
                    {"batch_id": {"$in": batch_ids}, "status": "failed"}
                )
                pending = await db.messages.count_documents(
                    {"batch_id": {"$in": batch_ids}, "status": {"$in": ["pending", "processing"]}}
                )
                c["live_sent"] = sent
                c["live_failed"] = failed
                c["live_pending"] = pending

            result.append(c)

        return {"campaigns": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/{campaign_id}/stop")
async def stop_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Emergency stop: cancel all pending batches for a campaign."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        service = BatchService(db)
        result = await service.stop_campaign(campaign_id, user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/campaigns/{campaign_id}")
async def get_campaign_details(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
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

        # Get live campaign_batches map for this campaign
        campaign_batches = await db.campaign_batches.find(
            {"campaign_id": campaign_id, "user_id": user_id},
            {"_id": 0}
        ).sort("batch_number", 1).to_list(1000)
        
        # Convert datetime fields
        if isinstance(campaign.get("created_at"), datetime):
            dt = campaign["created_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            campaign["created_at"] = dt.isoformat()
        if isinstance(campaign.get("updated_at"), datetime):
            dt = campaign["updated_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            campaign["updated_at"] = dt.isoformat()
        if isinstance(campaign.get("completed_at"), datetime):
            dt = campaign["completed_at"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            campaign["completed_at"] = dt.isoformat()
        campaign["_id"] = str(campaign["_id"])
        
        return {
            "campaign": campaign,
            "batches": batches,
            "campaign_batches": campaign_batches,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/stats")
async def get_queue_stats(
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db)
):
    """Get message queue statistics."""
    try:
        from services.scheduler_service import SchedulerWorker
        worker = SchedulerWorker(db)
        stats = await worker.get_queue_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Campaign Control Endpoints (Scheduler Integration)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Pause a sending campaign. Worker stops after finishing current item."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        result = await db.campaigns.update_one(
            {"_id": campaign_id, "user_id": user_id, "status": {"$in": ["sending", "pending", "in_progress"]}},
            {"$set": {"status": "paused", "updated_at": datetime.now(timezone.utc)}},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Campaign not found or cannot be paused")
        return {"message": "Campaign paused", "campaign_id": campaign_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Resume a paused campaign. Worker picks up items on next poll cycle."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        result = await db.campaigns.update_one(
            {"_id": campaign_id, "user_id": user_id, "status": "paused"},
            {"$set": {"status": "sending", "updated_at": datetime.now(timezone.utc)}},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Campaign not found or not paused")
        return {"message": "Campaign resumed", "campaign_id": campaign_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Cancel a campaign. Purge remaining pending queue items."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        # Set campaign to cancelled
        await db.campaigns.update_one(
            {"_id": campaign_id, "user_id": user_id},
            {"$set": {"status": "cancelled", "completed_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
        )

        # Cancel all pending/retry_wait queue items in messages
        queue_result = await db.messages.update_many(
            {"campaign_id": campaign_id, "status": {"$in": ["pending", "retry_wait"]}},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )

        # Cancel pending batches
        await db.batches.update_many(
            {"campaign_id": campaign_id, "status": {"$in": ["pending", "sending"]}},
            {"$set": {"status": "cancelled"}},
        )

        return {
            "message": "Campaign cancelled",
            "messages_cancelled": queue_result.modified_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/{campaign_id}/live-stats")
async def get_campaign_live_stats(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Real-time stats for the campaign monitor dashboard."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        campaign = await db.campaigns.find_one(
            {"_id": campaign_id, "user_id": user_id}
        )
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Aggregate from messages for real-time accuracy
        pipeline = [
            {"$match": {"campaign_id": campaign_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        counts = {}
        async for doc in db.messages.aggregate(pipeline):
            counts[doc["_id"]] = doc["count"]

        total = sum(counts.values())
        # Support both "sent" (new scheduler spec) and "delivered" (legacy)
        delivered = counts.get("sent", 0) + counts.get("delivered", 0)
        pending = counts.get("pending", 0)
        processing = counts.get("processing", 0)
        retry_wait = counts.get("retry_wait", 0)
        # Support both "failed_permanently" (new) and "failed_final" (legacy)
        failed_final = counts.get("failed_permanently", 0) + counts.get("failed_final", 0)
        cancelled = counts.get("cancelled", 0)

        # Convert datetimes
        c_status = campaign.get("status", "pending")
        created_at = campaign.get("created_at")
        if isinstance(created_at, datetime):
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            created_at = created_at.isoformat()

        completed_at = campaign.get("completed_at")
        if isinstance(completed_at, datetime):
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            completed_at = completed_at.isoformat()

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("campaign_name", ""),
            "status": c_status,
            "total_targeted": total,
            "delivered": delivered,
            "pending": pending + processing,
            "retry_wait": retry_wait,
            "failed_final": failed_final,
            "cancelled": cancelled,
            "completed_batches": campaign.get("completed_batches", 0),
            "total_batches": campaign.get("total_batches", 0),
            "segment_stats": campaign.get("segment_stats", {}),
            "created_at": created_at,
            "completed_at": completed_at,
            "progress_pct": round(delivered / total * 100, 1) if total > 0 else 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/{campaign_id}/dlq")
async def get_campaign_dlq(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Get all failed_final items for the Dead Letter Queue desk."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        # Verify campaign ownership
        campaign = await db.campaigns.find_one(
            {"_id": campaign_id, "user_id": user_id},
            {"_id": 1},
        )
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        items = await db.messages.find(
            {"campaign_id": campaign_id, "status": "failed_final"},
            {"_id": 0},
        ).sort("updated_at", -1).to_list(500)

        return {"dlq_items": items, "count": len(items)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Queue Item Action Endpoints (DLQ Resolution)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/queue/{item_id}/requeue")
async def requeue_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Re-queue a failed_final item back into the active queue."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")
        now = datetime.now()

        result = await db.messages.update_one(
            {"id": item_id, "user_id": user_id, "status": "failed_final"},
            {"$set": {
                "status": "pending",
                "retry_count": 0,
                "next_attempt_at": now,
                "error": None,
                "updated_at": now.isoformat(),
            }},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Item not found or not in failed_final")

        return {"message": "Item re-queued successfully", "item_id": item_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/{item_id}/resolve")
async def resolve_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """Mark a failed item as resolved, removing it from the DLQ view."""
    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        result = await db.messages.update_one(
            {"id": item_id, "user_id": user_id, "status": "failed_final"},
            {"$set": {
                "status": "resolved",
                "resolved_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Item not found or not in failed_final")

        return {"message": "Item marked as resolved", "item_id": item_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
