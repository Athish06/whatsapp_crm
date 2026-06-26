"""
Pydantic schemas/models for request and response validation.

Phase 1 Schema Refinement:
  - Added: OfferCreate, OfferResponse, OfferUpdate (new offers collection)
  - Added: upload_cycle to ShopCreate / ShopResponse
  - Added: period_tag, content_hash, row_count to FileMetadata

  - Added: previous_segment, segment_changed to CustomerInsightResponse
  - Added: campaign_id, offer_id, failure_reason to MessageResponse
  - Added: MonitoringStats response model
  - Removed: MessageQueueCreate / MessageQueueResponse (merged into messages)
  - Removed: CampaignBatchCreate / CampaignBatchResponse (merged into campaigns)
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


# ══════════════════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════════════════

class CustomerCategory(str, Enum):
    """
    Customer classification categories — 6-tier Hybrid RFM+B Intelligence.
    
    Waterfall order (Phase 1 additions in comments):

      Rule 1: VIP            — rfm_score ≥ 12 AND (m_score ≥ 4 OR f_score ≥ 4)
      Rule 2: AT_RISK        — r_score ≤ 2 + (f+m)≥5  OR  prev=VIP/Loyal AND recency_days≥30
      Rule 3: POTENTIAL_BULK — 5≤total≤11 AND b_score≥4
      Rule 4: LOYAL_FREQUENT — 5≤total≤11 AND f_score≥3 AND f≥m
      Rule 5: BORING         — everything else (display as "Occasional" in frontend)
    """

    VIP            = "vip"            # Champions
    AT_RISK        = "at_risk"        # Lapsing High-Potentials
    POTENTIAL_BULK = "potential_bulk" # Pantry Stockers
    LOYAL_FREQUENT = "loyal_frequent" # Daily Habit Shoppers
    BORING         = "boring"         # Occasional (low-engagement baseline)
    DORMANT        = "dormant"        # NEW: had transactions but none in current window


class BatchStatus(str, Enum):
    """Batch processing status."""
    PENDING   = "pending"
    SCHEDULED = "scheduled"
    SENDING   = "sending"
    COMPLETED = "completed"
    FAILED    = "failed"
    PAUSED    = "paused"


class MessageStatus(str, Enum):
    """Individual message lifecycle — 8 states (msg_queues merged in)."""
    PENDING           = "pending"
    PROCESSING        = "processing"
    SENT_TO_PROVIDER  = "sent_to_provider"
    SENT              = "sent"              # legacy compat
    DELIVERED         = "delivered"
    RETRY_WAIT        = "retry_wait"
    FAILED            = "failed"            # legacy compat
    FAILED_FINAL      = "failed_final"
    FAILED_PERMANENTLY = "failed_permanently"
    CANCELLED         = "cancelled"
    SKIPPED           = "skipped"           # NEW: e.g., expired offer


class MessageFailureReason(str, Enum):
    """Categorised failure reasons (Bug #12 resolution)."""
    RATE_LIMIT           = "rate_limit"
    NETWORK              = "network"
    INVALID_NUMBER       = "invalid_number"
    WHATSAPP_DISCONNECTED = "whatsapp_disconnected"  # NEW
    OFFER_EXPIRED        = "offer_expired"           # NEW
    OUTSIDE_HOURS        = "outside_working_hours"   # NEW
    UNKNOWN              = "unknown"


class CampaignStatus(str, Enum):
    """Campaign-level status for scheduler coordination."""
    PENDING   = "pending"
    SENDING   = "sending"
    PAUSED    = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    STOPPED   = "stopped"


class MessagePriority(int, Enum):
    """Message priority levels — Hybrid RFM+B Intelligence."""
    VIP            = 1
    AT_RISK        = 1

    POTENTIAL_BULK = 2
    LOYAL_FREQUENT = 3
    BORING         = 4
    DORMANT        = 5  # NEW: lowest priority


class ProductType(str, Enum):
    """Product type for intelligence filtering."""
    PREMIUM = "premium"
    BULK    = "bulk"
    DAILY   = "daily"


class DiscountType(str, Enum):
    """Offer discount types."""
    PERCENTAGE = "percentage"
    FLAT       = "flat"
    BOGO       = "bogo"  # buy-one-get-one


class OfferMode(str, Enum):
    """Offer application mode."""
    INDIVIDUAL = "individual"  # discount applies to each product independently
    COMBINED   = "combined"    # discount applies only when ALL products are purchased together


class UploadCycle(str, Enum):
    """Upload frequency for a shop (determines period_tag format)."""
    MONTHLY = "monthly"  # period_tag = "2026-06"
    WEEKLY  = "weekly"   # period_tag = "2026-06-W3"


# ══════════════════════════════════════════════════════════════════════════════
# Shop Models
# ══════════════════════════════════════════════════════════════════════════════

class ShopCreate(BaseModel):
    """Create shop request."""
    shop_name: str
    upload_cycle: UploadCycle = UploadCycle.MONTHLY  # NEW: defaults to monthly


class ShopUpdate(BaseModel):
    """Update shop fields."""
    shop_name: Optional[str] = None
    upload_cycle: Optional[UploadCycle] = None


class ShopResponse(BaseModel):
    """Shop response."""
    id: str
    user_id: str
    shop_name: str
    upload_cycle: str = "monthly"  # NEW
    created_at: datetime


# ══════════════════════════════════════════════════════════════════════════════
# Offers Models  (NEW — Phase 1)
# ══════════════════════════════════════════════════════════════════════════════

class OfferCreate(BaseModel):
    """Create an offer for a shop."""
    title: str
    description: Optional[str] = None
    discount_type: DiscountType
    discount_value: float                             # e.g. 20 (for 20% or ₹20 flat)
    offer_mode: str = "individual"                   # "individual" or "combined"
    product_ids: List[str] = []                      # linked products (can be empty → category-wide)
    category: Optional[str] = None                   # optional category-wide scope
    target_segments: List[str] = []                  # optional segment tags (empty = open to all)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: bool = True


class OfferUpdate(BaseModel):
    """Update existing offer."""
    title: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[float] = None
    offer_mode: Optional[str] = None
    product_ids: Optional[List[str]] = None
    category: Optional[str] = None
    target_segments: Optional[List[str]] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: Optional[bool] = None


class OfferResponse(BaseModel):
    """Offer response document."""
    id: str
    shop_id: str
    user_id: str
    title: str
    description: Optional[str] = None
    discount_type: str
    discount_value: float
    offer_mode: str = "individual"
    product_ids: List[str] = []
    category: Optional[str] = None
    target_segments: List[str] = []
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    is_active: bool
    created_at: str


# ══════════════════════════════════════════════════════════════════════════════
# Product Models
# ══════════════════════════════════════════════════════════════════════════════

class ProductInventoryCreate(BaseModel):
    """Create product inventory item request."""
    shop_id: str
    product_id: str
    name: str
    category: str
    price: float
    product_type: ProductType


class ProductInventoryResponse(ProductInventoryCreate):
    """Product inventory response."""
    id: str


# ══════════════════════════════════════════════════════════════════════════════
# Auth Schemas
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# Customer Schemas
# ══════════════════════════════════════════════════════════════════════════════

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
    shop_id: Optional[str] = None
    column_mapping: Dict[str, str]
    percentile: Optional[int] = 70


class CustomerInsightResponse(BaseModel):
    """Embedded insight data returned alongside a customer record."""
    customer_id: str
    segment: str
    previous_segment: Optional[str] = None       # NEW: segment before latest recalculation
    segment_changed: bool = False                 # NEW: True if segment differs from previous
    rfm_score: Optional[int] = None
    r_score: Optional[int] = None
    f_score: Optional[int] = None
    m_score: Optional[int] = None
    recency_days: Optional[int] = None
    frequency: Optional[int] = None
    monetary: Optional[float] = None
    favorite_category: Optional[str] = None
    last_calculated_at: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Template Schemas
# ══════════════════════════════════════════════════════════════════════════════

class MessageTemplateCreate(BaseModel):
    """Create message template request."""
    shop_id: Optional[str] = None
    name: str
    content: str
    segment: Optional[str] = "all"


class MessageTemplateResponse(BaseModel):
    """Message template response."""
    id: str
    name: str
    content: str
    placeholders: List[str]
    segment: str
    created_at: str


# ══════════════════════════════════════════════════════════════════════════════
# Batch Schemas
# ══════════════════════════════════════════════════════════════════════════════

class BatchCreate(BaseModel):
    """Create batch campaign request."""
    shop_id: Optional[str] = None
    campaign_name: Optional[str] = None
    file_id: Optional[str] = None
    template_id: Optional[str] = None
    segment_templates: Optional[Dict[str, str]] = None
    segment_offers: Optional[Dict[str, str]] = None   # NEW: segment → offer_id mapping
    customer_ids: List[str]
    batch_size: int
    start_time: datetime
    priority: int = 0
    ai_mode: bool = False
    enable_upsell: bool = False                       # NEW: enable upsell offer matching
    fixed_product: Optional[str] = None
    period_tag: Optional[str] = None                  # NEW: which period this campaign covers


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
    """Individual message response (absorbs msg_queues fields)."""
    id: str
    batch_id: str
    campaign_id: Optional[str] = None             # NEW: direct ref (no longer only on batch)
    customer_id: str
    phone_number: str
    customer_name: Optional[str] = None
    customer_segment: Optional[str] = None
    template_id: Optional[str] = None
    offer_id: Optional[str] = None                # NEW: linked offer
    message_content: str
    status: MessageStatus
    priority: int = 4
    scheduled_at: Optional[str] = None
    sent_at: Optional[str] = None
    retry_count: int = 0
    error_log: Optional[List[Dict[str, Any]]] = None  # NEW: structured list (was string)
    failure_reason: Optional[str] = None          # NEW: categorised failure
    user_id: Optional[str] = None
    shop_id: Optional[str] = None
    created_at: Optional[str] = None


class BatchSplitEstimate(BaseModel):
    """Batch split estimation response."""
    total_customers: int
    batch_size: int
    total_batches: int
    split_time_seconds: float
    estimated_completion_minutes: float


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard Schemas
# ══════════════════════════════════════════════════════════════════════════════

class DashboardStats(BaseModel):
    """Dashboard statistics response."""
    total_customers: int
    messages_sent: int
    messages_failed: int
    active_batches: int
    templates_count: int


class MonitoringStats(BaseModel):
    """
    Monitoring dashboard stats (Phase 5).
    Returned by monitoring endpoints for a shop/campaign.
    """
    total: int = 0
    sent: int = 0
    delivered: int = 0
    failed: int = 0
    pending: int = 0
    cancelled: int = 0
    skipped: int = 0
    retry_wait: int = 0
    failure_reasons: Dict[str, int] = {}         # {"rate_limit": 5, "invalid_number": 2}
    period_tag: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# File Upload Schemas  — enhanced with content_hash, period_tag, row_count
# ══════════════════════════════════════════════════════════════════════════════

class FileUploadResponse(BaseModel):
    """File upload response."""
    file_id: str
    file_name: str
    file_url: str
    file_size: int
    content_hash: Optional[str] = None    # NEW: SHA-256 hex
    period_tag: Optional[str] = None      # NEW: "2026-06" or "2026-06-W3"
    row_count: Optional[int] = None       # NEW: number of data rows
    uploaded_at: datetime
    duplicate: Optional[bool] = False
    can_reprocess: bool = True            # NEW: Bug #7 fix — allow re-process on hash match


class FileMetadata(BaseModel):
    """File metadata stored in database."""
    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str
    shop_id: Optional[str] = None
    data_purpose: Optional[str] = None
    file_name: str
    original_file_name: str
    file_url: str
    file_size: int
    file_type: str
    content_hash: Optional[str] = None   # NEW
    period_tag: Optional[str] = None     # NEW
    row_count: Optional[int] = None      # NEW
    uploaded_at: datetime
    b2_file_id: Optional[str] = None
    
    class Config:
        populate_by_name = True


class UserFilesResponse(BaseModel):
    """User files list response."""
    total_files: int
    files: List[FileMetadata]


# ══════════════════════════════════════════════════════════════════════════════
# Process File Request
# ══════════════════════════════════════════════════════════════════════════════

class ProcessFileRequest(BaseModel):
    """Request to process uploaded file with column mapping."""
    shop_id: Optional[str] = None
    column_mapping: Dict[str, str]
    percentile: Optional[int] = 70
    user_id: str
    period_tag: Optional[str] = None  # NEW: owner can override auto-detected period


# ══════════════════════════════════════════════════════════════════════════════
# Customer Behavior Map Models (legacy — kept for migration compatibility)
# ══════════════════════════════════════════════════════════════════════════════

class CustomerBehaviorMapCreate(BaseModel):
    """Create customer behavior map request (legacy)."""
    shop_id: str
    customer_id: str
    fav_items: List[str] = []
    recent_purchases: List[str] = []
    top_categories: List[str] = []


class CustomerBehaviorMapResponse(CustomerBehaviorMapCreate):
    """Customer behavior map response (legacy)."""
    id: str
