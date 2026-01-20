"""
Customer service for managing customer data.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import pandas as pd
from utils.classifier import parse_csv_file, classify_customers


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def upload_customers(
        self, 
        file_content: bytes, 
        filename: str, 
        user_id: str,
        file_url: str = None,
        file_id: str = None
    ) -> Dict[str, Any]:
        """Process and upload customers from CSV/Excel/PDF file.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            user_id: User ID
            file_url: URL of file in Backblaze B2 (optional, from file_service)
            file_id: File ID in files collection (optional, from file_service)
        """
        # Parse file
        df = parse_csv_file(file_content, filename)
        
        # Classify customers
        df, classifications = classify_customers(df)
        
        # Prepare customer documents with all available fields
        customers = []
        for _, row in df.iterrows():
            # Extract all columns from the row
            customer_data = row.to_dict()
            
            # Build customer document with standard fields
            customer_doc = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "name": str(customer_data.get('name', '')).strip(),
                "phone": str(customer_data.get('phone', '')).strip(),
                "email": str(customer_data.get('email', '')).strip(),
                "category": customer_data.get('category', 'regular'),
                "total_quantity": float(customer_data.get('total_quantity', 0)),
                "purchase_count": int(customer_data.get('purchase_count', 1)),
                "order_value": float(customer_data.get('order_value', 0)),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "source_file": filename,
            }
            
            # Add file reference if file was uploaded to cloud
            if file_url:
                customer_doc["file_url"] = file_url
            if file_id:
                customer_doc["file_id"] = file_id
            
            # Add any additional custom fields from the uploaded file
            # This allows flexibility for batch processing later
            additional_fields = {
                k: v for k, v in customer_data.items() 
                if k not in ['name', 'phone', 'email', 'category', 'total_quantity', 
                           'purchase_count', 'order_value'] and pd.notna(v)
            }
            
            if additional_fields:
                customer_doc['custom_fields'] = additional_fields
            
            customers.append(customer_doc)
        
        # Insert into database
        if customers:
            await self.db.customers.insert_many(customers)
        
        # Remove _id field added by MongoDB to avoid serialization issues
        customers_response = []
        for customer in customers:
            customer_copy = {k: v for k, v in customer.items() if k != '_id'}
            customers_response.append(customer_copy)
        
        return {
            "total_customers": len(customers_response),
            "classifications": classifications,
            "customers": customers_response
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
