"""
Template routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import MessageTemplateCreate, MessageTemplateResponse
from services import TemplateService
from middleware import get_current_user
from config import get_db

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("/create", response_model=MessageTemplateResponse)
async def create_template(
    template_data: MessageTemplateCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Create a new message template."""
    service = TemplateService(db)
    user_id = current_user.get("user_id") or current_user.get("id")
    template = await service.create_template(
        template_data.name,
        template_data.content,
        user_id,
        template_data.segment
    )
    return MessageTemplateResponse(**template)


@router.get("/list")
async def list_templates(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """List all templates for the current user."""
    service = TemplateService(db)
    user_id = current_user.get("user_id") or current_user.get("id")
    templates = await service.list_templates(user_id)
    return {"templates": templates}


@router.get("/{template_id}", response_model=MessageTemplateResponse)
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Get a specific template by ID."""
    service = TemplateService(db)
    user_id = current_user.get("user_id") or current_user.get("id")
    template = await service.get_template(template_id, user_id)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return MessageTemplateResponse(**template)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Delete a template."""
    service = TemplateService(db)
    user_id = current_user.get("user_id") or current_user.get("id")
    deleted = await service.delete_template(template_id, user_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {"message": "Template deleted successfully"}
