"""
Template service for managing message templates.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import re


class TemplateService:
    """Service for message template operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    @staticmethod
    def extract_placeholders(content: str) -> List[str]:
        """Extract placeholders from message template."""
        return re.findall(r'\{\{(\w+)\}\}', content)
    
    async def create_template(
        self, 
        name: str, 
        content: str, 
        user_id: str
    ) -> Dict[str, Any]:
        """Create a new message template."""
        placeholders = self.extract_placeholders(content)
        
        template_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "content": content,
            "placeholders": placeholders,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        await self.db.templates.insert_one(template_doc)
        return template_doc
    
    async def list_templates(self, user_id: str) -> List[Dict[str, Any]]:
        """List all templates for a user."""
        templates = await self.db.templates.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        
        return templates
    
    async def get_template(
        self, 
        template_id: str, 
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific template by ID."""
        template = await self.db.templates.find_one(
            {"id": template_id, "user_id": user_id},
            {"_id": 0}
        )
        return template
    
    async def delete_template(self, template_id: str, user_id: str) -> bool:
        """Delete a template."""
        result = await self.db.templates.delete_one(
            {"id": template_id, "user_id": user_id}
        )
        return result.deleted_count > 0
