"""
Authentication service for user registration and login.
"""
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import UserLogin, UserRegister, TokenResponse
from middleware import verify_password, get_password_hash, create_access_token


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def register(self, user_data: UserRegister) -> TokenResponse:
        """Register a new user."""
        # Check if user exists
        existing_user = await self.db.users.find_one(
            {"email": user_data.email}, 
            {"_id": 0}
        )
        if existing_user:
            raise ValueError("Email already registered")
        
        # Create user document
        user_doc = {
            "email": user_data.email,
            "full_name": user_data.full_name,
            "hashed_password": get_password_hash(user_data.password),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True
        }
        
        result = await self.db.users.insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        # Create token
        access_token = create_access_token(
            data={"sub": user_id, "email": user_data.email}
        )
        
        return TokenResponse(access_token=access_token)
    
    async def login(self, credentials: UserLogin) -> TokenResponse:
        """Authenticate user and return token."""
        # Find user
        user = await self.db.users.find_one(
            {"email": credentials.email},
            {"_id": 1, "email": 1, "hashed_password": 1, "is_active": 1}
        )
        
        if not user:
            raise ValueError("Invalid email or password")
        
        if not verify_password(credentials.password, user["hashed_password"]):
            raise ValueError("Invalid email or password")
        
        if not user.get("is_active", True):
            raise ValueError("Account is inactive")
        
        # Create token
        user_id = str(user["_id"])
        access_token = create_access_token(
            data={"sub": user_id, "email": user["email"]}
        )
        
        return TokenResponse(access_token=access_token)
