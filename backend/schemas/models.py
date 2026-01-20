"""
Pydantic schemas/models for request and response validation.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CustomerCategory(str, Enum):
    """Customer classification categories."""
    BULK_BUYER = "bulk_buyer"
    FREQUENT_CUSTOMER = "frequent_customer"
    BOTH = "both"
    REGULAR = "regular"


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
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


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

class CustomerUploadResponse(BaseModel):
    """Response for customer CSV upload."""
    total_customers: int
    classifications: Dict[str, int]
    customers: List[Dict[str, Any]]


# ============ Template Schemas ============

class MessageTemplateCreate(BaseModel):
    """Create message template request."""
    name: str
    content: str


class MessageTemplateResponse(BaseModel):
    """Message template response."""
    id: str
    name: str
    content: str
    placeholders: List[str]
    created_at: str


# ============ Batch Schemas ============

class BatchCreate(BaseModel):
    """Create batch campaign request."""
    template_id: str
    customer_ids: List[str]
    batch_size: int
    start_time: datetime
    priority: int = 0


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
