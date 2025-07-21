from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
import os
import shutil
import hashlib
import datetime
import pydicom
from pydicom.uid import generate_uid
from typing import Optional

from database import save_upload_record, save_dicom_metadata, save_ml_result, save_audit_log, save_wix_upload, get_user_uploads, get_upload_by_id, get_wix_upload_stats
from dicom_utils import convert_to_dicom, anonymize_dicom, encrypt_file
from fastapi.middleware.cors import CORSMiddleware

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS Middleware
origins = [
    "https://editor.wix.com",
    "https://<your-wix-site-url>" # Replace with your actual Wix site URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development, can be restricted later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Updated response model
class UploadResponse(BaseModel):
    upload_id: str
    message: str
    diagnosis: str
    confidence: float

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
        save_upload_record(upload_id, original_filename, ext, now, ip_address, encrypted_path, sha256_hash)

        # Save DICOM metadata
        save_dicom_metadata(upload_id, True, True, removed_tags, now)

        # Trigger ML model (mocked for now)
        diagnosis, confidence = "Tumor Detected", 0.89
        save_ml_result(upload_id, "v1.0", diagnosis, confidence, now)

        # Save to PostgreSQL wix_uploads table
        wix_saved = False
        if user_id:
            try:
                wix_saved = save_wix_upload(user_id, upload_id, now)
                if wix_saved:
                    print(f"Successfully saved to wix_uploads table: user_id={user_id}, upload_id={upload_id}")
                else:
                    print("Failed to save to wix_uploads table")
            except Exception as db_error:
                print(f"Database wix_uploads error: {str(db_error)}")
                # Don't fail the entire upload if database save fails
        else:
            print("No user ID provided, skipping wix_uploads table save")

        # Audit log
        audit_data = {"wix_saved": wix_saved}
        save_audit_log(upload_id, "upload_processed", now, ip_address, "success", audit_data)

        # ✅ Updated return with diagnosis and confidence
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
    """Manually save an upload to wix_uploads table (for testing or recovery)"""
    try:
        from datetime import datetime
        result = save_wix_upload(user_id, upload_id, datetime.utcnow())
        if result:
            return {"message": "Successfully saved to wix_uploads table", "user_id": user_id, "upload_id": upload_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to save to wix_uploads table")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving to database: {str(e)}")

@app.get("/stats")
async def get_upload_statistics():
    """Get upload statistics from the database"""
    try:
        stats = get_wix_upload_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")
