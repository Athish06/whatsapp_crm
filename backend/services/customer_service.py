"""
Customer service for managing customer data.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import uuid
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: Any):
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
        from utils.classifier import detect_columns
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
            "customer_id": None,
            "name": None,
            "phone": None,
        }
        
        # Customer ID field suggestions
        id_keywords = ['customer_id', 'cust_id', 'id', 'customer_no', 'customer_code']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw == col_lower or kw in col_lower for kw in id_keywords) and not mapping["customer_id"]:
                mapping["customer_id"] = col
                break

        # Name field suggestions
        name_keywords = ['name', 'customer', 'client', 'full_name', 'customer_name']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in name_keywords) and not mapping["name"]:
                # Avoid matching customer_id again
                if col != mapping.get("customer_id"):
                    mapping["name"] = col
                    break
        
        # Phone field suggestions
        phone_keywords = ['phone', 'mobile', 'contact', 'tel', 'cell', 'mobile_no']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in phone_keywords) and not mapping["phone"]:
                mapping["phone"] = col
                break
        
        return mapping
    
    async def upload_customers(
        self, 
        file_content: bytes, 
        filename: str, 
        user_id: str,
        shop_id: Optional[str] = None,
        file_url: str = None,
        file_id: str = None,
        campaign_id: str = None,
        column_mapping: Optional[Dict[str, str]] = None,
        percentile: int = 70
    ) -> Dict[str, Any]:
        """Process and upload customers from CSV/Excel file.
        
        In the 3-layer architecture, this stores ONLY core bio data:
            - customer_id (from CSV or auto-generated)
            - name
            - phone
            - email (optional)
            - user_id, shop_id
        
        RFM segmentation is NOT performed here. It is computed by
        recalculate_all_insights() after transactions are uploaded.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            user_id: User ID
            shop_id: Shop ID
            file_url: URL of file in Backblaze B2 (optional)
            file_id: File ID in files collection (optional)
            campaign_id: Campaign ID (optional)
            column_mapping: User-provided column mapping (optional)
            percentile: Deprecated — kept for backward compat
        """
        # Parse file
        df = self._parse_customer_csv(file_content, filename, column_mapping)
        
        # Prepare customer documents with ONLY core bio fields
        customers = []
        for _, row in df.iterrows():
            customer_data = row.to_dict()
            phone_value = str(customer_data.get('phone', '')).strip()

            # Blank phone rows cannot be safely upserted because phone is part of the unique key.
            if not phone_value:
                continue
            
            # Extract customer_id from CSV if available, else auto-generate
            csv_customer_id = str(customer_data.get('customer_id', '')).strip()
            
            customer_doc = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "shop_id": shop_id,
                "campaign_id": campaign_id,
                "customer_id": csv_customer_id if csv_customer_id else phone_value,  # Use phone as fallback ID
                "name": str(customer_data.get('name', '')).strip(),
                "phone": phone_value,
                "email": str(customer_data.get('email', '')).strip() if 'email' in customer_data else '',
                "segment": "boring",  # Default — will be overwritten by insights engine
                "category": "boring",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "source_file": filename,
            }
            
            # Add file reference if file was uploaded to cloud
            if file_url:
                customer_doc["file_url"] = file_url
            if file_id:
                customer_doc["file_id"] = file_id
            
            customers.append(customer_doc)

        # Deduplicate on the natural unique key before bulk upsert
        deduped_customers = []
        seen_keys = set()
        for customer in customers:
            key = (customer.get("user_id"), customer.get("shop_id"), customer.get("campaign_id"), customer.get("phone"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped_customers.append(customer)
        customers = deduped_customers
        
        # Overwrite snapshot per campaign container.
        delete_filter = {"user_id": user_id, "campaign_id": campaign_id, "shop_id": shop_id}
        if not campaign_id:
            delete_filter = {"user_id": user_id, "campaign_id": {"$exists": False}, "shop_id": shop_id}
        await self.db.customers.delete_many(delete_filter)

        # Insert/Update customers in database
        if customers:
            from pymongo import UpdateOne
            
            operations = []
            for customer in customers:
                operations.append(
                    UpdateOne(
                        {
                            "user_id": customer["user_id"],
                            "shop_id": customer.get("shop_id"),
                            "campaign_id": customer.get("campaign_id"),
                            "phone": customer["phone"],
                        },
                        {"$set": customer},
                        upsert=True
                    )
                )
            
            if operations:
                result = await self.db.customers.bulk_write(operations, ordered=False)
                logger.info(f"Upserted {result.upserted_count} new customers, modified {result.modified_count} existing")
        
        # After storing customers, trigger insights recalculation if transactions exist
        # This ensures segments get populated if transactions were already uploaded
        classifications = {
            "vip": 0,
            "at_risk": 0,
            "potential_bulk": 0,
            "loyal_frequent": 0,
            "boring": len(customers),  # Default all to boring until insights run
        }

        if shop_id:
            tx_count = await self.db.transactions.count_documents({"shop_id": shop_id})
            if tx_count > 0:
                # Transactions exist — run insights in background
                from services.insights_service import recalculate_all_insights
                insights_count = await recalculate_all_insights(self.db, shop_id)
                logger.info(f"Recalculated {insights_count} insights after customer upload")

                # Re-read classifications from customer_insights
                seg_pipeline = [
                    {"$match": {"shop_id": shop_id}},
                    {"$group": {"_id": "$segment", "count": {"$sum": 1}}},
                ]
                seg_cursor = self.db.customer_insights.aggregate(seg_pipeline)
                classifications = {
                    "vip": 0,
                    "at_risk": 0,
                    "potential_bulk": 0,
                    "loyal_frequent": 0,
                    "boring": 0,
                }
                async for doc in seg_cursor:
                    seg = doc["_id"] or "boring"
                    if seg in classifications:
                        classifications[seg] = doc["count"]
                    else:
                        classifications["boring"] += doc["count"]

                # Reload customers with updated segments
                customers = await self.db.customers.find(
                    {"user_id": user_id, "shop_id": shop_id},
                    {"_id": 0}
                ).to_list(10000)

        # Remove _id field added by MongoDB
        customers_response = []
        for customer in customers:
            customer_copy = {k: v for k, v in customer.items() if k != '_id'}
            customers_response.append(customer_copy)
        
        return {
            "total_customers": len(customers_response),
            "classifications": classifications,
            "customers": customers_response,
            "rfm_info": {
                "method": "Hybrid RFM+B Intelligence",
                "note": "RFM scores computed from transaction data via customer_insights pipeline"
            }
        }
    
    def _parse_customer_csv(
        self,
        file_content: bytes,
        filename: str,
        column_mapping: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """Parse customer CSV with the simplified 3-column schema.
        
        Expected CSV columns: customer_id, customer_name, mobile_no
        """
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif filename_lower.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError("Unsupported file format. Please upload CSV or Excel file.")
        
        # Apply user column mapping if provided
        if column_mapping:
            reverse = {v: k for k, v in column_mapping.items() if v and v != 'none' and v in df.columns}
            df = df.rename(columns=reverse)
        else:
            # Auto-standardize column names
            df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
            auto_map = {
                'customer_name': 'name',
                'customer': 'name',
                'full_name': 'name',
                'phone_number': 'phone',
                'mobile': 'phone',
                'mobile_no': 'phone',
                'contact': 'phone',
                'email_address': 'email',
                'cust_id': 'customer_id',
            }
            df.rename(columns=auto_map, inplace=True)
        
        # Validate required columns (name + phone)
        required_cols = ['name', 'phone']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Missing required columns: {', '.join(missing_cols)}. "
                f"Available columns: {', '.join(df.columns.tolist())}"
            )
        
        # Clean phone numbers
        if 'phone' in df.columns:
            df['phone'] = df['phone'].astype(str).str.replace(r'[\s\-\(\)]', '', regex=True)
        
        # Ensure optional columns exist
        if 'email' not in df.columns:
            df['email'] = ''
        if 'customer_id' not in df.columns:
            df['customer_id'] = ''
        
        return df
    
    async def list_customers(self, user_id: str, shop_id: Optional[str] = None) -> Dict[str, Any]:
        """List all customers for a user (optionally scoped to a shop)."""
        query = {"user_id": user_id}
        if shop_id:
            query["shop_id"] = shop_id
        customers = await self.db.customers.find(
            query,
            {"_id": 0}
        ).sort("uploaded_at", -1).to_list(1000)
        
        return {"customers": customers, "total": len(customers)}
    
    async def clear_customers(self, user_id: str, shop_id: Optional[str] = None) -> int:
        """Delete all customers for a user (optionally scoped to a shop)."""
        query = {"user_id": user_id}
        if shop_id:
            query["shop_id"] = shop_id
        result = await self.db.customers.delete_many(query)
        # Also clear insights for this shop
        if shop_id:
            await self.db.customer_insights.delete_many({"shop_id": shop_id})
        return result.deleted_count
    
    async def get_customers_by_file(self, file_id: str, user_id: str) -> Dict[str, Any]:
        """Get all customers associated with a specific file."""
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
        
        # Calculate classifications from the segment field (synced from insights)
        classifications = {
            "vip": 0,
            "at_risk": 0,
            "potential_bulk": 0,
            "loyal_frequent": 0,
            "boring": 0,
        }
        
        for customer in customers:
            segment = customer.get("segment") or customer.get("category") or "boring"
            if segment in classifications:
                classifications[segment] += 1
            else:
                classifications["boring"] += 1
        
        return {
            "total_customers": len(customers),
            "classifications": classifications,
            "customers": customers
        }
