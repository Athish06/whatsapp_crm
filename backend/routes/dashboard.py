"""
Dashboard routes for statistics.
"""
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import DashboardStats
from services import DashboardService
from middleware import get_current_user
from config import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get dashboard statistics for the current user."""
    service = DashboardService(db)
    stats = await service.get_stats(current_user["id"])
    return DashboardStats(**stats)
