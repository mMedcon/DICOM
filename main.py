from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
import os
import shutil
import hashlib
import datetime
import pydicom
from pydicom.uid import generate_uid

from database import save_upload_record, save_dicom_metadata, save_ml_result, save_audit_log
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
async def upload_image(request: Request):
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

        # Audit log
        save_audit_log(upload_id, "upload_processed", now, ip_address, "success", {})

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
