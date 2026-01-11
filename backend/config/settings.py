"""
Application settings and configuration.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # MongoDB
    mongo_url: str = "mongodb://localhost:27017"
    db_name: str = "whatsapp_crm"
    
    # Security
    jwt_secret_key: str = "your-secret-key-change-in-production-12345678900987654321"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    
    # CORS
    cors_origins: str = "*"
    
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
