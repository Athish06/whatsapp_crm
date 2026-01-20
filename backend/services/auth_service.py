"""
Authentication service for user registration and login.
"""
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from schemas import UserLogin, UserRegister, TokenResponse
from middleware import verify_password, get_password_hash, create_access_token
import random
import string


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    def generate_otp(self) -> str:
        """Generate a 6-digit OTP."""
        return ''.join(random.choices(string.digits, k=6))
    
    async def create_otp(self, email: str, purpose: str = "signup") -> str:
        """
        Create and store OTP for email verification.
        
        Args:
            email: User email
            purpose: "signup" or "reset_password"
            
        Returns:
            str: Generated OTP
        """
        otp = self.generate_otp()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        # Store OTP in database
        await self.db.otps.update_one(
            {"email": email, "purpose": purpose},
            {
                "$set": {
                    "email": email,
                    "otp": otp,
                    "purpose": purpose,
                    "expires_at": expiry.isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "verified": False
                }
            },
            upsert=True
        )
        
        return otp
    
    async def verify_otp(self, email: str, otp: str, purpose: str = "signup") -> bool:
        """
        Verify OTP for email.
        
        Args:
            email: User email
            otp: OTP to verify
            purpose: "signup" or "reset_password"
            
        Returns:
            bool: True if OTP is valid
        """
        otp_doc = await self.db.otps.find_one({
            "email": email,
            "otp": otp,
            "purpose": purpose,
            "verified": False
        })
        
        if not otp_doc:
            return False
        
        # Check if expired
        expiry = datetime.fromisoformat(otp_doc["expires_at"])
        if datetime.now(timezone.utc) > expiry:
            return False
        
        # Mark as verified
        await self.db.otps.update_one(
            {"_id": otp_doc["_id"]},
            {"$set": {"verified": True}}
        )
        
        return True
    
    async def register(self, user_data: UserRegister) -> TokenResponse:
        """Register a new user."""
        # Check if user exists
        existing_user = await self.db.users.find_one(
            {"email": user_data.email}, 
            {"_id": 0}
        )
        if existing_user:
            raise ValueError("Email already registered")
        
        # Check if email was verified via OTP
        verified_otp = await self.db.otps.find_one({
            "email": user_data.email,
            "purpose": "signup",
            "verified": True
        })
        
        # Create user document
        user_doc = {
            "email": user_data.email,
            "full_name": user_data.full_name,
            "hashed_password": get_password_hash(user_data.password),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True,
            "email_verified": bool(verified_otp)  # True if OTP was verified
        }
        
        result = await self.db.users.insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        # Create token
        access_token = create_access_token(
            data={"sub": user_id, "email": user_data.email}
        )
        
        return TokenResponse(access_token=access_token)
    
    async def verify_email(self, email: str, otp: str) -> bool:
        """Verify user email with OTP during signup."""
        # Just verify the OTP - user doesn't exist yet
        # The register function will check for verified OTP and set email_verified accordingly
        if not await self.verify_otp(email, otp, purpose="signup"):
            return False
        
        return True
    
    async def initiate_password_reset(self, email: str) -> bool:
        """Initiate password reset process."""
        # Check if user exists
        user = await self.db.users.find_one({"email": email})
        if not user:
            # For security, don't reveal if email exists
            return True
        
        # Generate and store OTP
        await self.create_otp(email, purpose="reset_password")
        return True
    
    async def reset_password(self, email: str, otp: str, new_password: str) -> bool:
        """Reset password with verified OTP."""
        # Verify OTP
        if not await self.verify_otp(email, otp, purpose="reset_password"):
            raise ValueError("Invalid or expired OTP")
        
        # Check if user exists
        user = await self.db.users.find_one({"email": email})
        if not user:
            raise ValueError("User not found")
        
        # Update password
        await self.db.users.update_one(
            {"email": email},
            {"$set": {"hashed_password": get_password_hash(new_password)}}
        )
        
        return True
    
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
