from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Header, Form, Query
from fastapi.responses import JSONResponse, FileResponse
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

from database import (
    save_upload_record, save_dicom_metadata, save_ml_result, save_audit_log, 
    save_user_upload, get_user_uploads, get_upload_by_id, get_upload_stats,
    save_batch_record, update_batch_progress, get_batch_status, get_user_batches
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

UPLOAD_DIR = "uploads"
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
    try:
        # Get filename from custom header (case-insensitive)
        original_filename = request.headers.get("x-file-name")
        if not original_filename:
            raise HTTPException(status_code=400, detail="X-File-Name header is missing.")

        # Get file content from the raw request body
        file_bytes = await request.body()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Request body is empty.")

        upload_id = str(uuid4())
        ext = os.path.splitext(original_filename)[-1].lower()
        now = datetime.datetime.utcnow()
        ip_address = request.client.host

        # Save original file temporarily from bytes
        temp_path = os.path.join(UPLOAD_DIR, f"{upload_id}{ext}")
        with open(temp_path, "wb") as buffer:
            buffer.write(file_bytes)

        # Calculate hash
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()

        # Convert to DICOM
        dicom_path = convert_to_dicom(temp_path, upload_id)

        # Anonymize
        anonymized_path, removed_tags = anonymize_dicom(dicom_path)

        # Encrypt
        encrypted_path = encrypt_file(anonymized_path)

        # Save upload record
        save_upload_record(upload_id, original_filename, ext, now, ip_address, encrypted_path, sha256_hash, None)

        # Save DICOM metadata
        save_dicom_metadata(upload_id, True, True, removed_tags, now)

        # Trigger ML model (mocked for now)
        diagnosis, confidence = "Tumor Detected", 0.89
        save_ml_result(upload_id, "v1.0", diagnosis, confidence, now)


        # Save to user_uploads table (generic, not Wix-specific)
        user_upload_saved = False
        if user_id:
            try:
                user_upload_saved = save_user_upload(user_id, upload_id, now)
                if user_upload_saved:
                    print(f"Successfully saved to user_uploads table: user_id={user_id}, upload_id={upload_id}")
                else:
                    print("Failed to save to user_uploads table")
            except Exception as db_error:
                print(f"Database user_uploads error: {str(db_error)}")
                # Don't fail the entire upload if database save fails
        else:
            print("No user ID provided, skipping user_uploads table save")

        # Audit log
        audit_data = {"user_upload_saved": user_upload_saved}
        save_audit_log(upload_id, "upload_processed", now, ip_address, "success", audit_data)

        # Updated return with diagnosis and confidence
        return UploadResponse(
            upload_id=upload_id,
            message="Upload and processing complete.",
            diagnosis=diagnosis,
            confidence=confidence
        )

    except Exception as e:
        print(f"Error during upload processing: {e}")
        import traceback
        traceback.print_exc()
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

@app.get("/upload/{upload_id}/details")
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

@app.get("/stats")
async def get_upload_statistics():
    """Get upload statistics from the database"""
    try:
        stats = get_upload_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")

# New Batch Upload Endpoints
@app.post("/upload/batch", response_model=BatchUploadResponse)
async def upload_batch(
    request: Request,
    user_id: Optional[str] = Header(None, alias="x-user-id")
):
    """
    Upload multiple files for batch processing
    Expects JSON payload with files data
    """
    try:
        # Get JSON payload containing files
        payload = await request.json()
        files_data = payload.get('files', [])
        
        if not files_data:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files_data) > 50:  # Limit batch size
            raise HTTPException(status_code=400, detail="Batch size too large (max 50 files)")
        
        # Generate batch ID
        batch_id = str(uuid4())
        total_files = len(files_data)
        
        # Save batch record
        save_batch_record(batch_id, user_id, total_files, "queued")
        
        # Queue the batch for background processing
        # Try Celery first, fallback to simple processor
        if celery_available:
            try:
                task = process_batch_upload.delay(batch_id, files_data, user_id)
                processing_method = "celery"
            except Exception as celery_error:
                print(f"Celery failed, using simple processor: {celery_error}")
                simple_processor.queue_batch_for_processing(batch_id, files_data, user_id)
                processing_method = "simple"
        else:
            simple_processor.queue_batch_for_processing(batch_id, files_data, user_id)
            processing_method = "simple"
        
        return BatchUploadResponse(
            batch_id=batch_id,
            message=f"Batch upload queued with {total_files} files ({processing_method})",
            total_files=total_files,
            status="queued"
        )
        
    except Exception as e:
        print(f"Error in batch upload: {e}")
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {str(e)}")

@app.get("/upload/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status_endpoint(batch_id: str):
    """Get the status of a batch upload"""
    try:
        batch_info = get_batch_status(batch_id)
        
        if not batch_info:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        progress_percentage = 0
        if batch_info['total_files'] > 0:
            progress_percentage = (batch_info['processed_files'] / batch_info['total_files']) * 100
        
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
        raise HTTPException(status_code=500, detail=f"Failed to get batch status: {str(e)}")

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
