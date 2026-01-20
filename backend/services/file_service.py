"""
File upload service for Backblaze B2 cloud storage.
Handles file uploads, URL generation, and MongoDB storage.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import hashlib
import uuid

from fastapi import UploadFile, HTTPException
from b2sdk.v2 import B2Api, InMemoryAccountInfo
from motor.motor_asyncio import AsyncIOMotorDatabase

from config import settings

logger = logging.getLogger(__name__)


class FileUploadService:
    """Service for handling file uploads to Backblaze B2."""
    
    def __init__(self):
        """Initialize Backblaze B2 API."""
        self.b2_api = None
        self.bucket = None
        self._initialize_b2()
    
    def _initialize_b2(self):
        """Initialize connection to Backblaze B2."""
        try:
            if not all([
                settings.b2_application_key_id,
                settings.b2_application_key,
                settings.b2_bucket_name
            ]):
                logger.warning("Backblaze B2 credentials not configured. File upload will not work.")
                return
            
            info = InMemoryAccountInfo()
            self.b2_api = B2Api(info)
            
            # Authorize account
            self.b2_api.authorize_account(
                "production",
                settings.b2_application_key_id,
                settings.b2_application_key
            )
            
            # Get bucket
            self.bucket = self.b2_api.get_bucket_by_name(settings.b2_bucket_name)
            logger.info(f"Connected to Backblaze B2 bucket: {settings.b2_bucket_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Backblaze B2: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Cloud storage service is not configured properly"
            )
    
    def _generate_unique_filename(self, original_filename: str, user_id: str) -> str:
        """
        Generate a unique filename to prevent collisions.
        
        Args:
            original_filename: Original name of the file
            user_id: User ID for namespacing
            
        Returns:
            Unique filename with path structure
        """
        # Extract file extension
        file_path = Path(original_filename)
        extension = file_path.suffix.lower()
        name_without_ext = file_path.stem
        
        # Generate unique identifier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        # Create structured path: users/{user_id}/files/{timestamp}_{uniqueid}_{filename}
        unique_filename = f"{timestamp}_{unique_id}_{name_without_ext}{extension}"
        full_path = f"users/{user_id}/files/{unique_filename}"
        
        return full_path
    
    async def upload_file(
        self,
        file: UploadFile,
        user_id: str,
        db: AsyncIOMotorDatabase
    ) -> Dict[str, Any]:
        """
        Upload file to Backblaze B2 and store metadata in MongoDB.
        
        Args:
            file: Uploaded file
            user_id: ID of the user uploading the file
            db: MongoDB database instance
            
        Returns:
            Dictionary with file metadata including URL
        """
        try:
            # Validate file
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")
            
            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            
            # Validate file size (max 100MB)
            max_size = 100 * 1024 * 1024  # 100MB
            if file_size > max_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File size exceeds maximum limit of 100MB"
                )
            
            # Generate unique filename
            unique_filename = self._generate_unique_filename(file.filename, user_id)
            
            # Determine content type
            content_type = file.content_type or "application/octet-stream"
            
            logger.info(f"Uploading file: {file.filename} ({file_size} bytes) for user {user_id}")
            
            # Upload to Backblaze B2
            file_info = self.bucket.upload_bytes(
                data_bytes=file_content,
                file_name=unique_filename,
                content_type=content_type,
                file_infos={
                    "user_id": user_id,
                    "original_filename": file.filename,
                    "uploaded_at": datetime.now().isoformat()
                }
            )
            
            # Get file URL
            file_url = self.b2_api.get_download_url_for_file_name(
                settings.b2_bucket_name,
                unique_filename
            )
            
            # Prepare metadata for MongoDB
            file_metadata = {
                "user_id": user_id,
                "file_name": unique_filename,
                "original_file_name": file.filename,
                "file_url": file_url,
                "file_size": file_size,
                "file_type": content_type,
                "uploaded_at": datetime.now(),
                "b2_file_id": file_info.id_,
            }
            
            # Store in MongoDB
            result = await db.files.insert_one(file_metadata)
            file_metadata["_id"] = str(result.inserted_id)
            
            logger.info(f"File uploaded successfully: {file.filename} -> {file_url}")
            
            return {
                "file_id": str(result.inserted_id),
                "file_name": file.filename,
                "file_url": file_url,
                "file_size": file_size,
                "uploaded_at": file_metadata["uploaded_at"],
                "user_id": user_id
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file: {str(e)}"
            )
    
    async def get_user_files(
        self,
        user_id: str,
        db: AsyncIOMotorDatabase,
        skip: int = 0,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get all files uploaded by a user.
        
        Args:
            user_id: User ID
            db: MongoDB database instance
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            Dictionary with total count and list of files
        """
        try:
            # Get total count
            total_files = await db.files.count_documents({"user_id": user_id})
            
            # Get files with pagination
            cursor = db.files.find({"user_id": user_id}).sort("uploaded_at", -1).skip(skip).limit(limit)
            files = await cursor.to_list(length=limit)
            
            # Convert ObjectId to string
            for file in files:
                file["_id"] = str(file["_id"])
            
            return {
                "total_files": total_files,
                "files": files
            }
            
        except Exception as e:
            logger.error(f"Error retrieving user files: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve files: {str(e)}"
            )
    
    async def delete_file(
        self,
        file_id: str,
        user_id: str,
        db: AsyncIOMotorDatabase
    ) -> Dict[str, str]:
        """
        Delete a file from Backblaze B2 and MongoDB.
        
        Args:
            file_id: File ID in MongoDB
            user_id: User ID (for authorization)
            db: MongoDB database instance
            
        Returns:
            Success message
        """
        try:
            from bson import ObjectId
            
            # Get file metadata
            file_doc = await db.files.find_one({
                "_id": ObjectId(file_id),
                "user_id": user_id
            })
            
            if not file_doc:
                raise HTTPException(
                    status_code=404,
                    detail="File not found or you don't have permission to delete it"
                )
            
            # Delete from Backblaze B2
            if file_doc.get("b2_file_id"):
                try:
                    file_version = self.b2_api.get_file_info(file_doc["b2_file_id"])
                    self.b2_api.delete_file_version(
                        file_doc["b2_file_id"],
                        file_doc["file_name"]
                    )
                    logger.info(f"Deleted file from B2: {file_doc['file_name']}")
                except Exception as e:
                    logger.warning(f"Could not delete file from B2: {str(e)}")
            
            # Delete from MongoDB
            await db.files.delete_one({"_id": ObjectId(file_id)})
            
            logger.info(f"File deleted successfully: {file_id}")
            
            return {
                "message": "File deleted successfully",
                "file_id": file_id
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete file: {str(e)}"
            )
    
    async def get_file_info(
        self,
        file_id: str,
        user_id: str,
        db: AsyncIOMotorDatabase
    ) -> Dict[str, Any]:
        """
        Get file information.
        
        Args:
            file_id: File ID in MongoDB
            user_id: User ID (for authorization)
            db: MongoDB database instance
            
        Returns:
            File metadata
        """
        try:
            from bson import ObjectId
            
            file_doc = await db.files.find_one({
                "_id": ObjectId(file_id),
                "user_id": user_id
            })
            
            if not file_doc:
                raise HTTPException(
                    status_code=404,
                    detail="File not found"
                )
            
            file_doc["_id"] = str(file_doc["_id"])
            return file_doc
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving file info: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve file info: {str(e)}"
            )


# Global instance
file_service = FileUploadService()
