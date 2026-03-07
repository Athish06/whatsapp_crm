"""
Customer service for managing customer data.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import pandas as pd
from utils.classifier import (
    parse_csv_file,
    classify_customers_rfm,
    detect_columns
)


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def detect_file_columns(
        self,
        file_content: bytes,
        filename: str
    ) -> Dict[str, Any]:
        """
        Detect columns in uploaded file and suggest mapping.
        
        Returns:
            Dictionary with detected columns and suggested mappings
        """
        columns = detect_columns(file_content, filename)
        
        # Suggest mapping based on common patterns
        suggested_mapping = self._suggest_column_mapping(columns)
        
        return {
            "columns": columns,
            "suggested_mapping": suggested_mapping
        }
    
    def _suggest_column_mapping(self, columns: List[str]) -> Dict[str, Optional[str]]:
        """
        Suggest mapping for detected columns based on common patterns.
        
        Returns:
            Dict mapping standard field names to suggested column names
        """
        columns_lower = [col.lower() for col in columns]
        mapping = {
            "name": None,
            "phone": None,
            "email": None,
            "quantity": None,  # Frontend uses 'quantity'
            "purchase_count": None,
            "total_spent": None,  # Frontend uses 'total_spent'
            "last_transaction_date": None  # For RFM Recency
        }
        
        # Name field suggestions
        name_keywords = ['name', 'customer', 'client', 'full_name', 'customer_name']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in name_keywords) and not mapping["name"]:
                mapping["name"] = col
                break
        
        # Phone field suggestions
        phone_keywords = ['phone', 'mobile', 'contact', 'tel', 'cell']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in phone_keywords) and not mapping["phone"]:
                mapping["phone"] = col
                break
        
        # Email field suggestions
        email_keywords = ['email', 'mail', 'e-mail']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in email_keywords) and not mapping["email"]:
                mapping["email"] = col
                break
        
        # Quantity field suggestions (frontend uses 'quantity')
        qty_keywords = ['quantity', 'qty', 'items', 'units', 'total_qty', 'total_quantity']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in qty_keywords) and not mapping["quantity"]:
                mapping["quantity"] = col
                break
        
        # Purchase count suggestions
        count_keywords = ['orders', 'purchase', 'count', 'visits', 'transactions']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in count_keywords) and not mapping["purchase_count"]:
                mapping["purchase_count"] = col
                break
        
        # Total spent suggestions (frontend uses 'total_spent')
        value_keywords = ['value', 'amount', 'total', 'revenue', 'spend', 'spent', 'price']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in value_keywords) and not mapping["total_spent"]:
                mapping["total_spent"] = col
                break
        
        # Last transaction date suggestions (for RFM Recency)
        date_keywords = ['date', 'last', 'recent', 'transaction', 'purchase_date', 'order_date', 'invoice_date']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in date_keywords) and not mapping["last_transaction_date"]:
                mapping["last_transaction_date"] = col
                break
        
        return mapping
    
    async def upload_customers(
        self, 
        file_content: bytes, 
        filename: str, 
        user_id: str,
        file_url: str = None,
        file_id: str = None,
        column_mapping: Optional[Dict[str, str]] = None,
        percentile: int = 70
    ) -> Dict[str, Any]:
        """Process and upload customers from CSV/Excel/PDF file with dynamic segmentation.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            user_id: User ID
            file_url: URL of file in Backblaze B2 (optional)
            file_id: File ID in files collection (optional)
            column_mapping: User-provided column mapping (optional)
            percentile: Percentile for dynamic thresholds (default 70)
        """
        # Parse file with column mapping
        df = parse_csv_file(file_content, filename, column_mapping)
        
        # Classify customers using RFM segmentation
        df, classifications, rfm_info = classify_customers_rfm(
            df,
            column_mapping=None  # Already applied in parse_csv_file
        )
        
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
                "segment": customer_data.get('segment', 'regular'),  # Add segment field
                "total_quantity": float(customer_data.get('total_quantity', 0)),
                "purchase_count": int(customer_data.get('purchase_count', 1)),
                "order_value": float(customer_data.get('order_value', 0)),
                "avg_items_per_order": float(customer_data.get('avg_items_per_order', 0)),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "source_file": filename,
            }
            
            # Add RFM scores if available
            if 'rfm_score' in customer_data and pd.notna(customer_data['rfm_score']):
                customer_doc['rfm_score'] = int(customer_data['rfm_score'])
            if 'r_score' in customer_data and pd.notna(customer_data['r_score']):
                customer_doc['r_score'] = int(customer_data['r_score'])
            if 'f_score' in customer_data and pd.notna(customer_data['f_score']):
                customer_doc['f_score'] = int(customer_data['f_score'])
            if 'm_score' in customer_data and pd.notna(customer_data['m_score']):
                customer_doc['m_score'] = int(customer_data['m_score'])
            if 'recency' in customer_data and pd.notna(customer_data['recency']):
                customer_doc['recency'] = float(customer_data['recency'])
            if 'frequency' in customer_data and pd.notna(customer_data['frequency']):
                customer_doc['frequency'] = int(customer_data['frequency'])
            if 'monetary' in customer_data and pd.notna(customer_data['monetary']):
                customer_doc['monetary'] = float(customer_data['monetary'])
            
            # Add file reference if file was uploaded to cloud
            if file_url:
                customer_doc["file_url"] = file_url
            if file_id:
                customer_doc["file_id"] = file_id
            
            # Add any additional custom fields from the uploaded file
            excluded_fields = {
                'name', 'phone', 'email', 'category', 'segment', 'total_quantity', 
                'purchase_count', 'order_value', 'avg_items_per_order',
                'rfm_score', 'r_score', 'f_score', 'm_score', 'recency', 'frequency', 'monetary',
                'recency_log', 'frequency_log', 'monetary_log', 'recency_scaled', 'frequency_scaled', 'monetary_scaled'
            }
            additional_fields = {
                k: v for k, v in customer_data.items() 
                if k not in excluded_fields and pd.notna(v)
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
            "customers": customers_response,
            "rfm_info": rfm_info
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
    
    async def get_customers_by_file(self, file_id: str, user_id: str) -> Dict[str, Any]:
        """Get all customers associated with a specific file."""
        # Query customers by file_id and user_id for security
        customers = await self.db.customers.find(
            {"file_id": file_id, "user_id": user_id},
            {"_id": 0}
        ).to_list(10000)
        
        if not customers:
            return {
                "total_customers": 0,
                "classifications": {},
                "customers": []
            }
        
        # Calculate classifications
        classifications = {
            "bulk_buyer": 0,
            "frequent_customer": 0,
            "both": 0,
            "regular": 0
        }
        
        for customer in customers:
            category = customer.get("category", "regular")
            if category in classifications:
                classifications[category] += 1
        
        return {
            "total_customers": len(customers),
            "classifications": classifications,
            "customers": customers
        }
