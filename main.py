from fastapi import FastAPI, File, Response, UploadFile, HTTPException, Request, Header, Form, Query
from fastapi.responses import JSONResponse, FileResponse
import psycopg2
from pydantic import BaseModel
from uuid import uuid4
import os
import shutil
import hashlib
import datetime
import pydicom
from pydicom.uid import generate_uid
from typing import Optional, List
import base64
import json
import logging
import logging.handlers
import sys

# Configure logging
def setup_logging():
    """
    Configure logging for the application with both console and file handlers.
    Creates a rotating file handler to prevent log files from growing too large.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

from database import (
    save_upload_record, save_dicom_metadata, save_ml_result, save_audit_log, 
    save_user_upload, get_user_uploads, get_upload_by_id, get_upload_stats,
    save_batch_record, update_batch_progress, get_batch_status, get_user_batches,
    get_all_uploads
)
from dicom_utils import convert_to_dicom, anonymize_dicom, encrypt_file
from fastapi.middleware.cors import CORSMiddleware

# Import processing modules
try:
    from job_queue import process_batch_upload
    celery_available = True
except ImportError:
    celery_available = False
    print("Celery not available, using simple processor only")

import simple_processor

from dicom_utils import dicom_to_png

UPLOAD_DIR = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS Middleware (update allowed origins as needed for your Next.js app)
origins = [
    "http://localhost:3000",  # Next.js local dev
    "https://myometrics.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Updated response model
class UploadResponse(BaseModel):
    upload_id: str
    message: str
    diagnosis: str
    confidence: float

class BatchUploadResponse(BaseModel):
    batch_id: str
    message: str
    total_files: int
    status: str

class BatchStatusResponse(BaseModel):
    batch_id: str
    status: str
    total_files: int
    processed_files: int
    progress_percentage: float
    created_at: str
    updated_at: Optional[str] = None

@app.post("/upload", response_model=UploadResponse)
async def upload_image(request: Request, user_id: Optional[str] = Header(None, alias="x-user-id")):
    """
    Handle single file upload, process it, and return results.
    
    This endpoint accepts an image file, converts it to DICOM format,
    anonymizes and encrypts it, then stores it in the database.
    """
    try:
        logger.info(f"Received upload request from IP: {request.client.host}")
        
        image_type = request.query_params.get("image_type")
        logger.debug(f"Image type: {image_type}")

        original_filename = request.headers.get("x-file-name")
        if not original_filename:
            logger.warning("Upload request missing X-File-Name header")
            raise HTTPException(status_code=400, detail="X-File-Name header is missing.")

        file_bytes = await request.body()
        if not file_bytes:
            logger.warning("Upload request has empty body")
            raise HTTPException(status_code=400, detail="Request body is empty.")

        upload_id = str(uuid4())
        ext = os.path.splitext(original_filename)[-1].lower()
        now = datetime.datetime.utcnow()
        ip_address = request.client.host

        logger.info(f"Processing upload: id={upload_id}, filename={original_filename}, size={len(file_bytes)} bytes")
        
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        temp_path = os.path.join(UPLOAD_DIR, f"{upload_id}{ext}")

        with open(temp_path, "wb") as buffer:
            buffer.write(file_bytes)
        logger.debug(f"Saved temporary file to {temp_path}")

        from database import cur
        logger.debug("Inserting upload record into database")
        cur.execute("""
            INSERT INTO public.uploads (
                id, original_filename, file_type, upload_time, uploader_ip, storage_path, sha256_hash, encrypted, status, batch_id, image_data, image_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, 'processed', %s, %s, %s)
        """, (
            upload_id, original_filename, ext, now, ip_address, temp_path, sha256_hash, None, psycopg2.Binary(file_bytes), image_type
        ))

        # Convert to DICOM
        logger.info(f"Converting file to DICOM format: {upload_id}")
        dicom_path = convert_to_dicom(temp_path, upload_id)
        logger.debug(f"DICOM conversion complete: {dicom_path}")

        # Anonymize
        logger.info(f"Anonymizing DICOM file: {upload_id}")
        anonymized_path, removed_tags = anonymize_dicom(dicom_path)
        logger.debug(f"Anonymization complete: {anonymized_path}, removed {len(removed_tags)} tags")

        # Encrypt
        logger.info(f"Encrypting anonymized DICOM file: {upload_id}")
        encrypted_path = encrypt_file(anonymized_path)
        logger.debug(f"Encryption complete: {encrypted_path}")

        # Save upload record
        logger.debug(f"Saving upload record to database: {upload_id}")
        save_upload_record(
            upload_id,
            original_filename,
            ext,
            now,
            ip_address,
            temp_path,  # Local path
            sha256_hash,
            None
        )

        # Save DICOM metadata
        logger.debug(f"Saving DICOM metadata to database: {upload_id}")
        save_dicom_metadata(upload_id, True, True, removed_tags, now)

        # Trigger ML model (mocked for now)
        logger.info(f"Running ML analysis on DICOM file: {upload_id}")
        diagnosis, confidence = "Tumor Detected", 0.89
        save_ml_result(upload_id, "v1.0", diagnosis, confidence, now)
        logger.debug(f"ML analysis complete: diagnosis={diagnosis}, confidence={confidence}")

        # Save to user_uploads table (generic, not Wix-specific)
        user_upload_saved = False
        if user_id:
            try:
                logger.info(f"Associating upload with user: user_id={user_id}, upload_id={upload_id}")
                user_upload_saved = save_user_upload(user_id, upload_id, now)
                if user_upload_saved:
                    logger.info(f"Successfully saved to user_uploads table: user_id={user_id}, upload_id={upload_id}")
                else:
                    logger.warning("Failed to save to user_uploads table")
            except Exception as db_error:
                logger.error(f"Database user_uploads error: {str(db_error)}")
                # Don't fail the entire upload if database save fails
        else:
            logger.info("No user ID provided, skipping user_uploads table save")

        # Audit log
        audit_data = {"user_upload_saved": user_upload_saved}
        logger.debug(f"Saving audit log: upload_id={upload_id}, action=upload_processed")
        save_audit_log(upload_id, "upload_processed", now, ip_address, "success", audit_data)

        logger.info(f"Upload processing complete: {upload_id}")
        
        # Updated return with diagnosis and confidence
        return UploadResponse(
            upload_id=upload_id,
            message="Upload and processing complete.",
            diagnosis=diagnosis,
            confidence=confidence
        )

    except Exception as e:
        logger.error(f"Error during upload processing: {e}")
        import traceback
        logger.error(traceback.format_exc())
        save_audit_log(None, "upload_failed", datetime.datetime.utcnow(), request.client.host, "error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Welcome to the DICOM upload API. Use /upload to post your DICOM files."}

@app.get("/health")
async def health_check():
    """Quick health check endpoint to test performance"""
    import time
    start_time = time.time()
    
    try:
        # Test database connection speed
        from database import cur
        cur.execute("SELECT 1")
        db_result = cur.fetchone()
        db_time = time.time() - start_time
        
        return {
            "status": "healthy",
            "database": "connected" if db_result else "failed",
            "response_time": f"{(time.time() - start_time):.3f}s",
            "db_query_time": f"{db_time:.3f}s"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "response_time": f"{(time.time() - start_time):.3f}s"
        }

@app.get("/user/{user_id}/uploads")
async def get_user_uploads_endpoint(user_id: str):
    """Get all uploads for a specific user from PostgreSQL"""
    try:
        uploads = get_user_uploads(user_id)
        return {
            "user_id": user_id,
            "uploads": uploads,
            "count": len(uploads)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve user uploads: {str(e)}")

@app.get("/upload/{upload_id}")
async def get_upload_details(upload_id: str):
    """Get upload data from PostgreSQL by upload ID"""
    try:
        upload_data = get_upload_by_id(upload_id)
        if upload_data:
            return upload_data
        else:
            raise HTTPException(status_code=404, detail="Upload not found in database")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve upload details: {str(e)}")

@app.post("/save-upload")
async def manual_save_upload(user_id: str, upload_id: str):
    """Manually save an upload to user_uploads table (for testing or recovery)"""
    try:
        from datetime import datetime
        result = save_user_upload(user_id, upload_id, datetime.utcnow())
        if result:
            return {"message": "Successfully saved to user_uploads table", "user_id": user_id, "upload_id": upload_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to save to user_uploads table")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving to database: {str(e)}")


# New endpoint: Get preprocessed (anonymized) DICOM file for clinicians to view
@app.get("/upload/{upload_id}/preprocessed-dicom")
async def get_preprocessed_dicom(upload_id: str):
    """Return the anonymized DICOM file for a given upload_id (before AI analysis)."""
    # The anonymized file is saved as uploads/{upload_id}_anon.dcm
    dicom_path = os.path.join(UPLOAD_DIR, f"{upload_id}_anon.dcm")
    if not os.path.exists(dicom_path):
        raise HTTPException(status_code=404, detail="Preprocessed DICOM file not found.")
    return FileResponse(dicom_path, media_type="application/dicom", filename=f"{upload_id}_anon.dcm")

@app.get("/uploads")
async def get_all_uploads_endpoint():
    """Get all uploads with their associated user IDs from PostgreSQL"""
    try:
        uploads = get_all_uploads()
        return {
            "uploads": uploads,
            "count": len(uploads)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve all uploads: {str(e)}")

@app.get("/stats")
async def get_upload_statistics():
    """Get upload statistics from the database"""
    try:
        stats = get_upload_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")

@app.post("/upload/batch", response_model=BatchUploadResponse)
async def upload_batch(
    request: Request,
    user_id: Optional[str] = Header(None, alias="x-user-id")
):
    """
    Upload multiple files for batch processing.
    
    This endpoint accepts a JSON payload with an array of files (base64 encoded),
    queues them for background processing, and returns a batch ID for tracking.
    
    The processing is done asynchronously using either Celery or a simple
    background processor, depending on availability.
    
    Args:
        request: The FastAPI request object containing the JSON payload
        user_id: Optional user ID from the X-User-ID header
        
    Returns:
        BatchUploadResponse with batch ID, status, and file count
    """
    try:
        logger.info(f"Received batch upload request from IP: {request.client.host}")
        
        # Get JSON payload containing files
        payload = await request.json()
        files_data = payload.get('files', [])
        
        if not files_data:
            logger.warning("Batch upload request with no files")
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files_data) > 50:  # Limit batch size
            logger.warning(f"Batch upload request with too many files: {len(files_data)}")
            raise HTTPException(status_code=400, detail="Batch size too large (max 50 files)")
        
        # Generate batch ID
        batch_id = str(uuid4())
        total_files = len(files_data)
        logger.info(f"Creating new batch: id={batch_id}, files={total_files}, user_id={user_id}")
        
        # Save batch record
        logger.debug(f"Saving batch record to database: {batch_id}")
        save_batch_record(batch_id, user_id, total_files, "queued")
        
        # Queue the batch for background processing
        # Try Celery first, fallback to simple processor
        if celery_available:
            try:
                logger.info(f"Queueing batch for Celery processing: {batch_id}")
                task = process_batch_upload.delay(batch_id, files_data, user_id)
                processing_method = "celery"
                logger.debug(f"Celery task created: {task.id}")
            except Exception as celery_error:
                logger.warning(f"Celery failed, using simple processor: {celery_error}")
                simple_processor.queue_batch_for_processing(batch_id, files_data, user_id)
                processing_method = "simple"
        else:
            logger.info(f"Celery not available, using simple processor for batch: {batch_id}")
            simple_processor.queue_batch_for_processing(batch_id, files_data, user_id)
            processing_method = "simple"
        
        logger.info(f"Batch queued successfully: id={batch_id}, method={processing_method}")
        return BatchUploadResponse(
            batch_id=batch_id,
            message=f"Batch upload queued with {total_files} files ({processing_method})",
            total_files=total_files,
            status="queued"
        )
        
    except Exception as e:
        logger.error(f"Error in batch upload: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {str(e)}")

@app.get("/upload/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status_endpoint(batch_id: str):
    """
    Get the status of a batch upload.
    
    This endpoint retrieves the current status of a batch upload, including
    the number of processed files and the overall progress percentage.
    
    Args:
        batch_id: The unique identifier of the batch
        
    Returns:
        BatchStatusResponse with batch status details
    """
    try:
        logger.info(f"Retrieving status for batch: {batch_id}")
        batch_info = get_batch_status(batch_id)
        
        if not batch_info:
            logger.warning(f"Batch not found: {batch_id}")
            raise HTTPException(status_code=404, detail="Batch not found")
        
        progress_percentage = 0
        if batch_info['total_files'] > 0:
            progress_percentage = (batch_info['processed_files'] / batch_info['total_files']) * 100
        
        logger.debug(f"Batch status: {batch_id}, status={batch_info['status']}, " +
                    f"progress={batch_info['processed_files']}/{batch_info['total_files']} " +
                    f"({round(progress_percentage, 2)}%)")
        
        return BatchStatusResponse(
            batch_id=batch_info['batch_id'],
            status=batch_info['status'],
            total_files=batch_info['total_files'],
            processed_files=batch_info['processed_files'],
            progress_percentage=round(progress_percentage, 2),
            created_at=batch_info['created_at'].isoformat() if batch_info['created_at'] else None,
            updated_at=batch_info['updated_at'].isoformat() if batch_info.get('updated_at') else None
        )
        
    except Exception as e:
        logger.error(f"Error retrieving batch status for {batch_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get batch status: {str(e)}")

# Shorthand route for easier frontend access
@app.get("/batch/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status_shorthand(batch_id: str):
    """Shorthand endpoint for batch status (redirects to full endpoint logic)"""
    return await get_batch_status_endpoint(batch_id)

# Additional shorthand routes for batch operations
@app.get("/batch/{batch_id}/files")
async def get_batch_files_shorthand(batch_id: str):
    """Shorthand endpoint for batch files"""
    return await get_batch_files(batch_id)

@app.get("/user/{user_id}/batches")
async def get_user_batches_endpoint(user_id: str):
    """Get all batch uploads for a user"""
    try:
        batches = get_user_batches(user_id)
        
        # Add progress percentage to each batch
        for batch in batches:
            if batch['total_files'] > 0:
                batch['progress_percentage'] = round(
                    (batch['processed_files'] / batch['total_files']) * 100, 2
                )
            else:
                batch['progress_percentage'] = 0
        
        return {
            "user_id": user_id,
            "batches": batches,
            "count": len(batches)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve user batches: {str(e)}")

@app.get("/upload/batch/{batch_id}/files")
async def get_batch_files(batch_id: str):
    """Get all files in a batch"""
    try:
        # Get files for this batch
        from database import cur
        cur.execute("""
            SELECT 
                u.id as upload_id,
                u.original_filename,
                u.file_type,
                u.status,
                u.upload_time,
                ml.diagnosis,
                ml.confidence_score
            FROM public.uploads u
            LEFT JOIN public.ml_results ml ON u.id = ml.upload_id
            WHERE u.batch_id = %s
            ORDER BY u.upload_time
        """, (batch_id,))
        
        columns = [desc[0] for desc in cur.description]
        results = cur.fetchall()
        files = [dict(zip(columns, row)) for row in results]
        
        return {
            "batch_id": batch_id,
            "files": files,
            "count": len(files)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve batch files: {str(e)}")

@app.get("/queue/status")
async def get_queue_status():
    """Get Redis queue status and cleanup statistics"""
    try:
        if celery_available:
            from job_queue import cleanup_redis_queue
            # Get queue cleanup statistics
            cleanup_stats = cleanup_redis_queue()
            
            # Get Celery inspect for active tasks
            from celery import current_app
            inspect = current_app.control.inspect()
            
            try:
                active_tasks = inspect.active()
                scheduled_tasks = inspect.scheduled()
                reserved_tasks = inspect.reserved()
                
                return {
                    "status": "available",
                    "celery_available": True,
                    "cleanup_stats": cleanup_stats,
                    "active_tasks": active_tasks or {},
                    "scheduled_tasks": scheduled_tasks or {},
                    "reserved_tasks": reserved_tasks or {},
                    "message": "Queue status retrieved successfully"
                }
            except Exception as inspect_error:
                return {
                    "status": "partial",
                    "celery_available": True,
                    "cleanup_stats": cleanup_stats,
                    "inspect_error": str(inspect_error),
                    "message": "Queue cleanup stats available, but worker inspection failed"
                }
        else:
            return {
                "status": "unavailable",
                "celery_available": False,
                "message": "Celery not available, using simple processor"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "celery_available": celery_available
        }

@app.get("/upload/{upload_id}/info")
async def get_image_info(upload_id: str):
    """
    Returns metadata about the uploaded image file (not the DICOM metadata).
    """
    from database import cur
    cur.execute("""
        SELECT original_filename, file_type, upload_time, storage_path, image_type
        FROM public.uploads
        WHERE id = %s
    """, (upload_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found in database")
    original_filename, file_type, upload_time, storage_path, image_type = row
    exists = storage_path and os.path.exists(storage_path)
    return {
        "upload_id": upload_id,
        "original_filename": original_filename,
        "file_type": file_type,
        "upload_time": upload_time,
        "storage_path": storage_path,
        "image_type": image_type,
        "exists": exists
    }

@app.get("/upload/{upload_id}/file")
async def get_uploaded_file(upload_id: str):
    from database import cur
    cur.execute("""
        SELECT original_filename, file_type, image_data
        FROM public.uploads
        WHERE id = %s
    """, (upload_id,))
    row = cur.fetchone()
    if not row or not row[2]:
        raise HTTPException(status_code=404, detail="Image not found in database")
    original_filename, file_type, image_data = row
    ext = os.path.splitext(original_filename)[-1].lower()
    if ext == ".png":
        mime = "image/png"
    elif ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".bmp":
        mime = "image/bmp"
    elif ext == ".gif":
        mime = "image/gif"
    else:
        mime = "application/octet-stream"
    return Response(content=image_data, media_type=mime, headers={"Content-Disposition": f"inline; filename={original_filename}"})

@app.get("/upload/{upload_id}/preview")
async def get_preview(upload_id: str):
    for ext in [".jpg", ".jpeg", ".png"]:
        img_path = os.path.join(UPLOAD_DIR, f"{upload_id}{ext}")
        if os.path.exists(img_path):
            return FileResponse(img_path, media_type="image/jpeg", filename=f"{upload_id}{ext}")
    dicom_path = os.path.join(UPLOAD_DIR, f"{upload_id}.dcm")
    png_path = os.path.join(UPLOAD_DIR, f"{upload_id}.png")
    if os.path.exists(dicom_path):
        if not os.path.exists(png_path):
            dicom_to_png(dicom_path, png_path)
        return FileResponse(png_path, media_type="image/png", filename=f"{upload_id}.png")
    raise HTTPException(status_code=404, detail="Preview not found")
