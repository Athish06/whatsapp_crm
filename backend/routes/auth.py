"""
Authentication routes.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import UserLogin, UserRegister, TokenResponse
from services import AuthService
from config import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])


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
