"""
Database configuration and connection management for MongoDB.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os


class Database:
    """MongoDB connection manager with singleton pattern."""
    
    client: Optional[AsyncIOMotorClient] = None
    
    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        """Get the MongoDB client instance."""
        if cls.client is None:
            mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
            cls.client = AsyncIOMotorClient(mongo_url)
        return cls.client
    
    @classmethod
    def get_database(cls):
        """Get the database instance."""
        db_name = os.environ.get('DB_NAME', 'whatsapp_crm')
        return cls.get_client()[db_name]
    
    @classmethod
    async def close(cls):
        """Close the MongoDB connection."""
        if cls.client is not None:
            cls.client.close()
            cls.client = None


# Convenience function for dependency injection
def get_db():
    """Get database instance for FastAPI dependency injection."""
    return Database.get_database()
