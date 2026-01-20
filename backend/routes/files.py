"""
File upload and management routes.
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from typing import List, Optional
import logging

from config import Database
from middleware.auth import get_current_user
from schemas.models import FileUploadResponse, UserFilesResponse
from services.file_service import file_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="CSV file to upload"),
    current_user: dict = Depends(get_current_user),
    db=Depends(Database.get_database)
):
    """
    Upload a CSV file to Backblaze B2 cloud storage.
    
    - **file**: CSV file to upload (max 100MB)
    - Returns file metadata including download URL
    - Files are linked to the authenticated user
    - Multiple files per user are supported
    """
    try:
        # Validate file type (CSV)
        if not file.filename.lower().endswith('.csv'):
            raise HTTPException(
                status_code=400,
                detail="Only CSV files are allowed"
            )
        
        # Get user ID
        user_id = current_user["user_id"]
        
        # Upload file
        result = await file_service.upload_file(
            file=file,
            user_id=user_id,
            db=db
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in upload endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload file"
        )


@router.get("/my-files", response_model=UserFilesResponse)
async def get_my_files(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records"),
    current_user: dict = Depends(get_current_user),
    db=Depends(Database.get_database)
):
    """
    Get all files uploaded by the authenticated user.
    
    - Returns list of files with metadata
    - Supports pagination with skip and limit
    - Sorted by upload date (newest first)
    """
    try:
        user_id = current_user["user_id"]
        
        result = await file_service.get_user_files(
            user_id=user_id,
            db=db,
            skip=skip,
            limit=limit
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving user files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve files"
        )


@router.get("/file/{file_id}")
async def get_file_info(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(Database.get_database)
):
    """
    Get information about a specific file.
    
    - **file_id**: MongoDB file ID
    - Returns complete file metadata including URL
    - Only file owner can access
    """
    try:
        user_id = current_user["user_id"]
        
        file_info = await file_service.get_file_info(
            file_id=file_id,
            user_id=user_id,
            db=db
        )
        
        return file_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving file info: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve file information"
        )


@router.delete("/file/{file_id}")
async def delete_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(Database.get_database)
):
    """
    Delete a file from cloud storage and database.
    
    - **file_id**: MongoDB file ID
    - Deletes from both Backblaze B2 and MongoDB
    - Only file owner can delete
    """
    try:
        user_id = current_user["user_id"]
        
        result = await file_service.delete_file(
            file_id=file_id,
            user_id=user_id,
            db=db
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete file"
        )


@router.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(..., description="Multiple CSV files to upload"),
    current_user: dict = Depends(get_current_user),
    db=Depends(Database.get_database)
):
    """
    Upload multiple CSV files at once.
    
    - **files**: List of CSV files (max 100MB each)
    - Returns list of uploaded file metadata
    - All files are linked to the authenticated user
    """
    try:
        user_id = current_user["user_id"]
        results = []
        errors = []
        
        for file in files:
            try:
                # Validate file type
                if not file.filename.lower().endswith('.csv'):
                    errors.append({
                        "filename": file.filename,
                        "error": "Only CSV files are allowed"
                    })
                    continue
                
                # Upload file
                result = await file_service.upload_file(
                    file=file,
                    user_id=user_id,
                    db=db
                )
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error uploading {file.filename}: {str(e)}")
                errors.append({
                    "filename": file.filename,
                    "error": str(e)
                })
        
        return {
            "uploaded": len(results),
            "failed": len(errors),
            "files": results,
            "errors": errors if errors else None
        }
        
    except Exception as e:
        logger.error(f"Error in multiple upload endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload files"
        )
