"""
Customer service for managing customer data.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
from utils.classifier import parse_csv_file, classify_customers


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def upload_customers(
        self, 
        file_content: bytes, 
        filename: str, 
        user_id: str
    ) -> Dict[str, Any]:
        """Process and upload customers from CSV/Excel file."""
        # Parse file
        df = parse_csv_file(file_content, filename)
        
        # Classify customers
        df, classifications = classify_customers(df)
        
        # Prepare customer documents
        customers = []
        for _, row in df.iterrows():
            customer_doc = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": row.get('name', ''),
                "phone": str(row.get('phone', '')),
                "email": row.get('email', ''),
                "category": row.get('category', 'regular'),
                "total_quantity": float(row.get('total_quantity', 0)),
                "purchase_count": int(row.get('purchase_count', 0)),
                "order_value": float(row.get('order_value', 0)),
                "product_category": row.get('product_category', row.get('category', '')),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            customers.append(customer_doc)
        
        # Insert into database
        if customers:
            await self.db.customers.insert_many(customers)
        
        return {
            "total_customers": len(customers),
            "classifications": classifications,
            "customers": customers
        }
    
    async def list_customers(self, user_id: str) -> Dict[str, Any]:
        """List all customers for a user."""
        customers = await self.db.customers.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("uploaded_at", -1).to_list(1000)
        
        return {"customers": customers, "total": len(customers)}
    
    async def clear_customers(self, user_id: str) -> int:
        """Delete all customers for a user."""
        result = await self.db.customers.delete_many({"user_id": user_id})
        return result.deleted_count
