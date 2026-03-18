"""
Pydantic schemas/models for request and response validation.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CustomerCategory(str, Enum):
    """Customer classification categories - Hybrid RFM+B Intelligence."""
    VIP = "vip"                          # Champions (RFM >= 12)
    AT_RISK = "at_risk"                  # Lapsing High-Potentials (R=1, Total>4)
    POTENTIAL_BULK = "potential_bulk"    # Pantry Stockers (5-11, High Bulkiness)
    LOYAL_FREQUENT = "loyal_frequent"    # Daily Habit Shoppers (5-11, F>=M)
    BORING = "boring"                    # Low-engagement Baseline (RFM <= 4)


class BatchStatus(str, Enum):
    """Batch processing status."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class MessageStatus(str, Enum):
    """Individual message status."""
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class MessagePriority(int, Enum):
    """Message priority levels - Hybrid RFM+B Intelligence."""
    VIP = 1                # VIP Champions (Retain gold assets)
    AT_RISK = 1            # At-Risk (Urgent - prevent churn)
    POTENTIAL_BULK = 2     # Potential Bulk (Increase spend per visit)
    LOYAL_FREQUENT = 3     # Loyal Frequent (Reward the habit)
    BORING = 4             # Boring (Low priority)


# ============ Auth Schemas ============

class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    full_name: str


class VerifyOTPRequest(BaseModel):
    """OTP verification request."""
    email: EmailStr
    otp: str


class SendOTPRequest(BaseModel):
    """Request to send/resend OTP."""
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password with OTP."""
    email: EmailStr
    otp: str
    new_password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


# ============ Customer Schemas ============

class ColumnDetectionResponse(BaseModel):
    """Response for column detection."""
    columns: List[str]
    suggested_mapping: Dict[str, Optional[str]]


class CustomerUploadResponse(BaseModel):
    """Response for customer CSV upload."""
    total_customers: int
    classifications: Dict[str, int]
    customers: List[Dict[str, Any]]
    rfm_info: Optional[Dict[str, Any]] = None
    thresholds: Optional[Dict[str, Any]] = None  # Deprecated: kept for backwards compatibility


class CustomerUploadWithMappingRequest(BaseModel):
    """Request for uploading customers with column mapping."""
    column_mapping: Dict[str, str]
    percentile: Optional[int] = 70


# ============ Template Schemas ============

class MessageTemplateCreate(BaseModel):
    """Create message template request."""
    name: str
    content: str
    segment: Optional[str] = "all"  # "all", "both" (VIP), "bulk_buyer", "frequent_customer", "regular"


class MessageTemplateResponse(BaseModel):
    """Message template response."""
    id: str
    name: str
    content: str
    placeholders: List[str]
    segment: str
    created_at: str


# ============ Batch Schemas ============

class BatchCreate(BaseModel):
    """Create batch campaign request."""
    campaign_name: Optional[str] = None  # Campaign name for tracking
    file_id: Optional[str] = None  # File ID for campaign tracking
    template_id: Optional[str] = None  # For backwards compatibility (single template)
    segment_templates: Optional[Dict[str, str]] = None  # For segment-based templates
    customer_ids: List[str]
    batch_size: int
    start_time: datetime
    priority: int = 0


class BatchUpdateRequest(BaseModel):
    """Edit scheduled batch request."""
    start_time: Optional[datetime] = None
    template_id: Optional[str] = None
    segment_templates: Optional[Dict[str, str]] = None


class BatchResponse(BaseModel):
    """Batch campaign response."""
    id: str
    template_id: str
    total_customers: int
    batch_size: int
    start_time: str
    status: BatchStatus
    success_count: int
    failed_count: int
    pending_count: int
    created_at: str
    priority: int


class MessageResponse(BaseModel):
    """Individual message response."""
    id: str
    batch_id: str
    customer_id: str
    phone_number: str
    message_content: str
    status: MessageStatus
    sent_at: Optional[str] = None
    error: Optional[str] = None


class BatchSplitEstimate(BaseModel):
    """Batch split estimation response."""
    total_customers: int
    batch_size: int
    total_batches: int
    split_time_seconds: float
    estimated_completion_minutes: float


# ============ Dashboard Schemas ============

class DashboardStats(BaseModel):
    """Dashboard statistics response."""
    total_customers: int
    messages_sent: int
    messages_failed: int
    active_batches: int
    templates_count: int


# ============ File Upload Schemas ============

class FileUploadResponse(BaseModel):
    """File upload response."""
    file_id: str
    file_name: str
    file_url: str
    file_size: int
    uploaded_at: datetime
    duplicate: Optional[bool] = False  # Flag for duplicate file detection


# ============ Campaign Batch Schemas (New) ============

class CampaignBatchCreate(BaseModel):
    """Create campaign batch request."""
    campaign_name: str
    file_id: Optional[str] = None
    segment_templates: Dict[str, str]  # segment -> template_id mapping
    total_customers: int
    segment_breakdown: Dict[str, int]  # segment -> count


class CampaignBatchResponse(BaseModel):
    """Campaign batch response."""
    id: str
    user_id: str
    campaign_name: str
    total_customers: int
    segment_breakdown: Dict[str, int]
    created_at: datetime
    status: BatchStatus


# ============ Message Queue Schemas (New) ============

class MessageQueueCreate(BaseModel):
    """Create message in queue."""
    batch_id: str
    customer_id: str
    phone: str
    message_body: str
    scheduled_at: datetime
    priority: int  # 1-4 based on RFM segment


class MessageQueueResponse(BaseModel):
    """Message queue item response."""
    id: str
    user_id: str
    batch_id: str
    customer_id: str
    phone: str
    message_body: str
    scheduled_at: datetime
    status: MessageStatus
    priority: int
    retry_count: int
    error_log: Optional[str] = None
    processed_at: Optional[datetime] = None


class ProcessFileRequest(BaseModel):
    """Request to process uploaded file with column mapping."""
    column_mapping: Dict[str, str]
    percentile: Optional[int] = 70
    user_id: str


class FileMetadata(BaseModel):
    """File metadata stored in database."""
    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str
    file_name: str
    original_file_name: str
    file_url: str
    file_size: int
    file_type: str
    uploaded_at: datetime
    b2_file_id: Optional[str] = None
    
    class Config:
        populate_by_name = True


class UserFilesResponse(BaseModel):
    """User files list response."""
    total_files: int
    files: List[FileMetadata]
