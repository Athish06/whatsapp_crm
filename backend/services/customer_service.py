"""
Customer service for managing customer data.
Per schema spec: customers = identity-only (name, phone, email, city, first_seen, last_seen).
RFM / segment data lives exclusively in customer_insights.
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
            "city": None,
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

        # City field suggestions
        city_keywords = ['city', 'town', 'location', 'area', 'district', 'place']
        for col, col_lower in zip(columns, columns_lower):
            if any(kw in col_lower for kw in city_keywords) and not mapping["city"]:
                mapping["city"] = col
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
        percentile: int = 70,
        period_tag: str = None
    ) -> Dict[str, Any]:
        """Process and upload customers from CSV/Excel file.
        
        Per schema spec, stores ONLY identity/bio data:
            - customer_id (natural key from CSV, or phone as fallback)
            - name, phone, email, city
            - first_seen (set on first insert, never updated)
            - last_seen (updated every re-upload)
            - user_id, shop_id, source_file, uploaded_at

        RFM segmentation is NOT stored here. It is computed exclusively
        by recalculate_all_insights() and lives in customer_insights.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            user_id: User ID
            shop_id: Shop ID
            file_url: URL of file in Backblaze B2 (optional)
            file_id: File ID in files collection (optional)
            campaign_id: Campaign ID (optional, kept for file linkage)
            column_mapping: User-provided column mapping (optional)
            percentile: Deprecated — kept for backward compat
        """
        # Parse file
        df = self._parse_customer_csv(file_content, filename, column_mapping)
        
        now = datetime.now(timezone.utc).isoformat()

        # Prepare customer documents with ONLY identity fields
        customers = []
        for _, row in df.iterrows():
            customer_data = row.to_dict()
            phone_value = str(customer_data.get('phone', '')).strip()

            # Blank phone rows cannot be safely upserted (phone is part of the unique key)
            if not phone_value:
                continue
            
            # Extract customer_id from CSV if available, else use phone as fallback
            csv_customer_id = str(customer_data.get('customer_id', '')).strip()
            city_value = str(customer_data.get('city', '')).strip()

            customer_doc = {
                "user_id": user_id,
                "shop_id": shop_id,
                "customer_id": csv_customer_id if csv_customer_id else phone_value,
                "name": str(customer_data.get('name', '')).strip(),
                "phone": phone_value,
                "email": str(customer_data.get('email', '')).strip() if 'email' in customer_data else '',
                "city": city_value,
                "last_seen": now,
                "uploaded_at": now,
                "source_file": filename,
                "period_tag": period_tag,
            }
            
            # Add file reference if file was uploaded to cloud
            if file_url:
                customer_doc["file_url"] = file_url
            if file_id:
                customer_doc["file_id"] = file_id
            if campaign_id:
                customer_doc["campaign_id"] = campaign_id

            customers.append(customer_doc)

        # Deduplicate on (shop_id, phone) before bulk upsert
        deduped_customers = []
        seen_keys = set()
        for customer in customers:
            key = (customer.get("shop_id"), customer.get("phone"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped_customers.append(customer)
        customers = deduped_customers
        
        # Upsert: set first_seen only on insert, always update last_seen
        if customers:
            from pymongo import UpdateOne
            
            operations = []
            for customer in customers:
                # Separate first_seen — only set on insert
                set_fields = {k: v for k, v in customer.items()}
                operations.append(
                    UpdateOne(
                        {
                            "shop_id": customer.get("shop_id"),
                            "phone": customer["phone"],
                        },
                        {
                            "$set": set_fields,
                            "$setOnInsert": {
                                "first_seen": now,
                                "id": str(uuid.uuid4()),
                            },
                        },
                        upsert=True
                    )
                )
            
            if operations:
                result = await self.db.customers.bulk_write(operations, ordered=False)
                logger.info(f"Upserted {result.upserted_count} new customers, modified {result.modified_count} existing")
        
        # After storing customers, trigger insights recalculation if transactions exist
        classifications = {
            "vip": 0,
            "at_risk": 0,
            "potential_bulk": 0,
            "loyal_frequent": 0,
            "boring": len(customers),  # Default all to boring until insights run
        }

        if shop_id:
            # Read classifications from customer_insights if they exist
            seg_pipeline = [
                {"$match": {"shop_id": shop_id}},
                {"$group": {"_id": "$segment", "count": {"$sum": 1}}},
            ]
            seg_cursor = self.db.customer_insights.aggregate(seg_pipeline)
            has_insights = False
            async for doc in seg_cursor:
                if not has_insights:
                    classifications = {
                        "vip": 0,
                        "at_risk": 0,
                        "potential_bulk": 0,
                        "loyal_frequent": 0,
                        "boring": 0,
                    }
                    has_insights = True
                seg = doc["_id"] or "boring"
                if seg in classifications:
                    classifications[seg] = doc["count"]
                else:
                    classifications["boring"] += doc["count"]


        # Return customers without _id
        customers_response = await self.db.customers.find(
            {"user_id": user_id, "shop_id": shop_id},
            {"_id": 0}
        ).to_list(10000)

        # Merge segment/RFM fields from customer_insights for each customer
        if shop_id and customers_response:
            insights_cursor = self.db.customer_insights.find({"shop_id": shop_id})
            insights = {doc["customer_id"]: doc async for doc in insights_cursor}
            
            for c in customers_response:
                cust_key = c.get("customer_id") or c.get("phone", "")
                insight = insights.get(cust_key)
                if insight:
                    c["segment"] = insight.get("segment", "boring")
                    c["rfm_score"] = insight.get("rfm_score")
                    c["r_score"] = insight.get("r_score")
                    c["f_score"] = insight.get("f_score")
                    c["m_score"] = insight.get("m_score")
                    c["b_score"] = insight.get("b_score")
                    c["recency_days"] = insight.get("recency_days")
                    c["frequency"] = insight.get("frequency")
                    c["monetary"] = insight.get("monetary")
                    c["favorite_category"] = insight.get("favorite_category")
                    c["top_categories"] = insight.get("top_categories", [])
                else:
                    c["segment"] = "boring"

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
        """Parse customer CSV with the simplified schema.
        
        Supported columns: customer_id, name, phone, email, city
        Required: name, phone
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
                'town': 'city',
                'location': 'city',
                'area': 'city',
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
        
        # Ensure optional columns exist with empty defaults
        for optional_col in ['email', 'customer_id', 'city']:
            if optional_col not in df.columns:
                df[optional_col] = ''
        
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
        
        # Merge segment/RFM fields from customer_insights for each customer
        if shop_id and customers:
            insights_cursor = self.db.customer_insights.find({"shop_id": shop_id})
            insights = {doc["customer_id"]: doc async for doc in insights_cursor}
            
            for c in customers:
                cust_key = c.get("customer_id") or c.get("phone", "")
                insight = insights.get(cust_key)
                if insight:
                    c["segment"] = insight.get("segment", "boring")
                    c["rfm_score"] = insight.get("rfm_score")
                    c["r_score"] = insight.get("r_score")
                    c["f_score"] = insight.get("f_score")
                    c["m_score"] = insight.get("m_score")
                    c["b_score"] = insight.get("b_score")
                    c["recency_days"] = insight.get("recency_days")
                    c["frequency"] = insight.get("frequency")
                    c["monetary"] = insight.get("monetary")
                    c["favorite_category"] = insight.get("favorite_category")
                    c["top_categories"] = insight.get("top_categories", [])
                else:
                    c["segment"] = "boring"
        
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
        
        # Get classifications from customer_insights (source of truth)
        shop_ids = list({c.get("shop_id") for c in customers if c.get("shop_id")})
        classifications = {
            "vip": 0,
            "at_risk": 0,
            "potential_bulk": 0,
            "loyal_frequent": 0,
            "boring": 0,
        }
        
        # Fetch insights and merge into customers
        insights = {}
        for sid in shop_ids:
            insights_cursor = self.db.customer_insights.find({"shop_id": sid})
            async for doc in insights_cursor:
                insights[(sid, doc["customer_id"])] = doc
                
            seg_pipeline = [
                {"$match": {"shop_id": sid}},
                {"$group": {"_id": "$segment", "count": {"$sum": 1}}},
            ]
            async for doc in self.db.customer_insights.aggregate(seg_pipeline):
                seg = doc["_id"] or "boring"
                if seg in classifications:
                    classifications[seg] += doc["count"]
                else:
                    classifications["boring"] += doc["count"]

        # Merge insights into customer records
        for c in customers:
            sid = c.get("shop_id")
            cust_id = c.get("customer_id") or c.get("phone", "")
            insight = insights.get((sid, cust_id))
            if insight:
                c["segment"] = insight.get("segment", "boring")
                c["rfm_score"] = insight.get("rfm_score")
                c["r_score"] = insight.get("r_score")
                c["f_score"] = insight.get("f_score")
                c["m_score"] = insight.get("m_score")
                c["b_score"] = insight.get("b_score")
                c["recency_days"] = insight.get("recency_days")
                c["frequency"] = insight.get("frequency")
                c["monetary"] = insight.get("monetary")
                c["favorite_category"] = insight.get("favorite_category")
                c["top_categories"] = insight.get("top_categories", [])
            else:
                c["segment"] = "boring"

        return {
            "total_customers": len(customers),
            "classifications": classifications,
            "customers": customers
        }
