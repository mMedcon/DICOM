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

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# ✅ Updated response model
class UploadResponse(BaseModel):
    upload_id: str
    message: str
    diagnosis: str
    confidence: float

@app.post("/upload", response_model=UploadResponse)
async def upload_image(request: Request, file: UploadFile = File(...)):
    try:
        upload_id = str(uuid4())
        original_filename = file.filename
        ext = os.path.splitext(original_filename)[-1].lower()
        now = datetime.datetime.utcnow()
        ip_address = request.client.host

        # Save original file temporarily
        temp_path = os.path.join(UPLOAD_DIR, f"{upload_id}{ext}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Calculate hash
        with open(temp_path, "rb") as f:
            sha256_hash = hashlib.sha256(f.read()).hexdigest()

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
        save_audit_log(None, "upload_failed", datetime.datetime.utcnow(), request.client.host, "error", {"error": str(e)})
        raise HTTPException(status_code=500, detail="File upload failed.")
