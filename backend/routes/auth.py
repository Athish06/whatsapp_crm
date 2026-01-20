"""
Authentication routes.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import (
    UserLogin, UserRegister, TokenResponse, 
    SendOTPRequest, VerifyOTPRequest,
    ForgotPasswordRequest, ResetPasswordRequest
)
from services import AuthService
from config import get_db
from utils.email_service import send_otp_email, send_password_changed_email

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/send-otp")
async def send_otp(
    request: SendOTPRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Send OTP to email for signup verification."""
    try:
        service = AuthService(db)
        
        # Check if email already exists
        existing_user = await db.users.find_one({"email": request.email})
        if existing_user and existing_user.get("email_verified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered and verified"
            )
        
        # Generate and send OTP
        otp = await service.create_otp(request.email, purpose="signup")
        
        if not send_otp_email(request.email, otp, purpose="verification"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP email"
            )
        
        return {"message": "OTP sent successfully", "email": request.email}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/verify-otp")
async def verify_otp(
    request: VerifyOTPRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Verify OTP for email."""
    try:
        service = AuthService(db)
        
        if not await service.verify_email(request.email, request.otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )
        
        return {"message": "Email verified successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegister,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Register a new user and set JWT token in cookie."""
    try:
        service = AuthService(db)
        token_response = await service.register(user_data)
        
        # Set JWT token in secure HTTP-only cookie
        response.set_cookie(
            key="access_token",
            value=token_response.access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=60 * 60 * 24 * 7  # 7 days
        )
        
        return token_response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Authenticate user and set JWT token in cookie."""
    try:
        service = AuthService(db)
        token_response = await service.login(credentials)
        
        # Set JWT token in secure HTTP-only cookie
        response.set_cookie(
            key="access_token",
            value=token_response.access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=60 * 60 * 24 * 7  # 7 days
        )
        
        return token_response
    except ValueError as e:
        if "inactive" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post("/logout")
async def logout(response: Response):
    """Logout user by clearing the JWT cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Initiate password reset process."""
    try:
        service = AuthService(db)
        
        # Check if user exists
        user = await db.users.find_one({"email": request.email})
        if not user:
            # For security, don't reveal if email exists
            return {"message": "If the email exists, a reset code has been sent"}
        
        # Generate and send OTP
        otp = await service.create_otp(request.email, purpose="reset_password")
        
        if not send_otp_email(request.email, otp, purpose="reset"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send reset code"
            )
        
        return {"message": "If the email exists, a reset code has been sent"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Reset password with OTP verification."""
    try:
        service = AuthService(db)
        
        # Reset password
        if not await service.reset_password(request.email, request.otp, request.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to reset password"
            )
        
        # Get user info for confirmation email
        user = await db.users.find_one({"email": request.email})
        if user:
            send_password_changed_email(request.email, user.get("full_name", "User"))
        
        return {"message": "Password reset successfully"}
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
