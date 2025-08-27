import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any
from celery import Celery
from database import (
    save_upload_record, save_dicom_metadata, save_ml_result, 
    save_audit_log, save_user_upload, save_batch_record, 
    update_batch_progress, get_batch_status
)
from dicom_utils import convert_to_dicom, anonymize_dicom, encrypt_file, detect_file_type
import hashlib
import tempfile

# Initialize Celery
celery_app = Celery(
    'dicom_processor',
    broker='redis://localhost:6379/0',  # Redis as message broker
    backend='redis://localhost:6379/0'  # Redis as result backend
)

# Celery configuration - Windows compatible
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes max per task
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    worker_prefetch_multiplier=1,  # Process one task at a time per worker
    # Windows-specific settings
    worker_pool='solo',  # Use solo pool instead of prefork for Windows
    task_always_eager=False,  # Ensure tasks run asynchronously
)

@celery_app.task(bind=True)
def process_batch_upload(self, batch_id: str, files_data: List[Dict], user_id: str = None):
    """
    Process a batch of uploaded files in the background
    
    Args:
        batch_id (str): Unique batch identifier
        files_data (List[Dict]): List of file information
        user_id (str): Optional user ID
    """
    try:
        print(f"🚀 Starting batch processing for batch_id: {batch_id}")
        print(f"📁 Processing {len(files_data)} files for user: {user_id}")
        
        total_files = len(files_data)
        processed_files = 0
        failed_files = 0
        results = []
        
        # Update batch status to processing
        print(f"📊 Updating batch status to processing...")
        update_batch_progress(batch_id, processed_files, total_files, "processing")
        print(f"✅ Batch status updated successfully")
        
        for i, file_info in enumerate(files_data):
            try:
                print(f"🔄 Processing file {i+1}/{total_files}: {file_info.get('filename', 'unknown')}")
                
                # Update task progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'batch_id': batch_id,
                        'current': processed_files,
                        'total': total_files,
                        'processing_file': file_info.get('filename', 'unknown')
                    }
                )
                
                # Process individual file
                result = process_single_file(file_info, batch_id, user_id)
                results.append(result)
                
                if result['success']:
                    processed_files += 1
                    print(f"✅ File {i+1} processed successfully")
                else:
                    failed_files += 1
                    print(f"❌ File {i+1} failed: {result.get('error', 'Unknown error')}")
                    
                # Update batch progress in database
                update_batch_progress(batch_id, processed_files, total_files, "processing")
                
            except Exception as file_error:
                print(f"💥 Critical error processing file {i+1} ({file_info.get('filename', 'unknown')}): {file_error}")
                import traceback
                traceback.print_exc()
                failed_files += 1
                results.append({
                    'filename': file_info.get('filename', 'unknown'),
                    'success': False,
                    'error': str(file_error)
                })
        
        # Final status update
        final_status = "completed" if failed_files == 0 else "completed_with_errors"
        update_batch_progress(batch_id, processed_files, total_files, final_status)
        
        print(f"🎉 Batch processing completed!")
        print(f"📊 Results: {processed_files}/{total_files} files processed successfully")
        print(f"❌ Failed files: {failed_files}")
        
        return {
            'batch_id': batch_id,
            'status': final_status,
            'total_files': total_files,
            'processed_files': processed_files,
            'failed_files': failed_files,
            'results': results
        }
        
    except Exception as e:
        print(f"💥 Critical batch processing error: {e}")
        import traceback
        traceback.print_exc()
        update_batch_progress(batch_id, processed_files, total_files, "failed")
        raise e

def process_single_file(file_info: Dict, batch_id: str, user_id: str = None) -> Dict:
    """Process a single file from the batch"""
    filename = "unknown"
    try:
        filename = file_info.get('filename', 'unknown')
        file_content = file_info.get('content')  # Base64 encoded content
        
        print(f"🔍 Processing file: {filename}")
        
        if not file_content:
            raise ValueError("File content is missing from file_info")
        
        # Decode file content
        import base64
        print(f"📄 Decoding base64 content...")
        file_bytes = base64.b64decode(file_content)
        print(f"✅ File decoded, size: {len(file_bytes)} bytes")
        
        # Generate upload ID
        upload_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[-1].lower()
        now = datetime.utcnow()
        
        # Create temporary file
        print(f"📁 Creating temporary file...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        print(f"✅ Temporary file created: {temp_path}")
        
        try:
            # Detect file type
            print(f"🔍 Detecting file type...")
            file_type = detect_file_type(file_bytes, filename)
            print(f"✅ File type detected: {file_type}")
            
            # Calculate hash
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            
            if file_type == 'dicom':
                print(f"🏥 Processing existing DICOM file...")
                # Handle existing DICOM files
                dicom_path = temp_path
                # Still anonymize existing DICOM
                anonymized_path, removed_tags = anonymize_dicom(dicom_path)
            else:
                print(f"🖼️ Converting image to DICOM...")
                # Convert image to DICOM
                dicom_path = convert_to_dicom(temp_path, upload_id)
                # Anonymize converted DICOM
                anonymized_path, removed_tags = anonymize_dicom(dicom_path)
            
            print(f"🔒 Encrypting file...")
            # Encrypt the anonymized file
            encrypted_path = encrypt_file(anonymized_path)
            
            print(f"💾 Saving to database...")
            # Save to database
            save_upload_record(upload_id, filename, ext, now, "batch_upload", encrypted_path, sha256_hash, batch_id)
            save_dicom_metadata(upload_id, True, True, removed_tags, now)
            
            # Mock ML result (replace with actual AI model)
            diagnosis, confidence = "Processing Complete", 0.95
            save_ml_result(upload_id, "v1.0", diagnosis, confidence, now)
            
            # Save user upload association
            if user_id:
                save_user_upload(user_id, upload_id, now)
            
            # Audit log
            save_audit_log(upload_id, "batch_processed", now, "batch_upload", "success", {
                "batch_id": batch_id,
                "file_type": file_type
            })
            
            print(f"✅ File {filename} processed successfully!")
            
            return {
                'filename': filename,
                'upload_id': upload_id,
                'success': True,
                'diagnosis': diagnosis,
                'confidence': confidence,
                'file_type': file_type
            }
            
        finally:
            # Clean up temporary files
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    print(f"🗑️ Cleaned up temporary file: {temp_path}")
            except Exception as cleanup_error:
                print(f"⚠️ Warning: Could not clean up temp file {temp_path}: {cleanup_error}")
                
    except Exception as e:
        print(f"💥 Critical error processing file {filename}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'filename': filename,
            'success': False,
            'error': str(e)
        }
