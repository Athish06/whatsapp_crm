"""
Authentication routes.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import UserLogin, UserRegister, TokenResponse
from services import AuthService
from config import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegister, 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Register a new user."""
    try:
        service = AuthService(db)
        return await service.register(user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin, 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Authenticate user and return token."""
    try:
        service = AuthService(db)
        return await service.login(credentials)
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
