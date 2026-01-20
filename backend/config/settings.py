"""
Application settings and configuration.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # MongoDB Configuration
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name: str = os.getenv("DB_NAME", "whatsapp_crm")
    
    # JWT Security Configuration
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "default-insecure-key-change-immediately")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
    
    # CORS Configuration
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    
    # Debug Mode
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Email Configuration
    sender_email: str = os.getenv("SENDER_EMAIL", "")
    google_app_password: str = os.getenv("GOOGLE_APP_PASSWORD", "")
    
    # Backblaze B2 Configuration
    b2_application_key_id: str = os.getenv("B2_APPLICATION_KEY_ID", "")
    b2_application_key: str = os.getenv("B2_APPLICATION_KEY", "")
    b2_bucket_name: str = os.getenv("B2_BUCKET_NAME", "")
    b2_bucket_id: str = os.getenv("B2_BUCKET_ID", "")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
