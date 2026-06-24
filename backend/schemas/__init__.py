"""
Schemas module for Pydantic models.
Phase 1: Added Offer models, UploadCycle, DiscountType, MonitoringStats,
         MessageFailureReason, CustomerInsightResponse, FileUploadResponse.
"""
from schemas.models import (
    # ── Enums ────────────────────────────────────────────────────────────────
    CustomerCategory,
    BatchStatus,
    MessageStatus,
    MessageFailureReason,
    CampaignStatus,
    MessagePriority,
    ProductType,
    DiscountType,
    UploadCycle,
    # ── Auth ─────────────────────────────────────────────────────────────────
    UserLogin,
    UserRegister,
    VerifyOTPRequest,
    SendOTPRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    # ── Shop ─────────────────────────────────────────────────────────────────
    ShopCreate,
    ShopUpdate,
    ShopResponse,
    # ── Offers (NEW) ─────────────────────────────────────────────────────────
    OfferCreate,
    OfferUpdate,
    OfferResponse,
    # ── Customers ────────────────────────────────────────────────────────────
    CustomerUploadResponse,
    ColumnDetectionResponse,
    CustomerUploadWithMappingRequest,
    CustomerInsightResponse,
    # ── Templates ────────────────────────────────────────────────────────────
    MessageTemplateCreate,
    MessageTemplateResponse,
    # ── Batches / Messages ───────────────────────────────────────────────────
    BatchCreate,
    BatchUpdateRequest,
    BatchResponse,
    MessageResponse,
    BatchSplitEstimate,
    # ── Dashboard / Monitoring ───────────────────────────────────────────────
    DashboardStats,
    MonitoringStats,
    # ── Files ────────────────────────────────────────────────────────────────
    FileUploadResponse,
    FileMetadata,
    UserFilesResponse,
    ProcessFileRequest,
)

__all__ = [
    # Enums
    "CustomerCategory",
    "BatchStatus",
    "MessageStatus",
    "MessageFailureReason",
    "CampaignStatus",
    "MessagePriority",
    "ProductType",
    "DiscountType",
    "UploadCycle",
    # Auth
    "UserLogin",
    "UserRegister",
    "VerifyOTPRequest",
    "SendOTPRequest",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    "TokenResponse",
    # Shop
    "ShopCreate",
    "ShopUpdate",
    "ShopResponse",
    # Offers
    "OfferCreate",
    "OfferUpdate",
    "OfferResponse",
    # Customers
    "CustomerUploadResponse",
    "ColumnDetectionResponse",
    "CustomerUploadWithMappingRequest",
    "CustomerInsightResponse",
    # Templates
    "MessageTemplateCreate",
    "MessageTemplateResponse",
    # Batches / Messages
    "BatchCreate",
    "BatchUpdateRequest",
    "BatchResponse",
    "MessageResponse",
    "BatchSplitEstimate",
    # Dashboard / Monitoring
    "DashboardStats",
    "MonitoringStats",
    # Files
    "FileUploadResponse",
    "FileMetadata",
    "UserFilesResponse",
    "ProcessFileRequest",
]
