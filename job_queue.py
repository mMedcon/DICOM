import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any
import logging
from celery import Celery
from database import (
    save_upload_record, save_dicom_metadata, save_ml_result, 
    save_audit_log, save_user_upload, save_batch_record, 
    update_batch_progress, get_batch_status
)
from dicom_utils import convert_to_dicom, anonymize_dicom, encrypt_file, detect_file_type
import hashlib
import tempfile

# Get logger
logger = logging.getLogger(__name__)

# Handle both local and Render Redis URLs
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery with environment-aware Redis URL
celery_app = Celery(
    'dicom_processor',
    broker=redis_url,
    backend=redis_url
)


# Celery configuration - Windows compatible with Redis cleanup
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
    # Redis cleanup settings
    result_expires=3600,  # Results expire after 1 hour (3600 seconds)
    task_ignore_result=False,  # Keep results but expire them
    # Cleanup settings
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks to prevent memory leaks
    task_acks_late=True,  # Only acknowledge task after completion
)

def cleanup_redis_queue():
    """
    Manual cleanup function to remove old/stale tasks from Redis.
    
    This function connects to Redis, finds Celery task keys without
    expiration times, and sets them to expire after 1 hour to prevent
    Redis memory from growing indefinitely.
    
    Call this periodically or when Redis memory is getting full.
    
    Returns:
        dict: Cleanup statistics including number of keys and expirations set
    """
    try:
        import redis
        logger.info("Starting Redis queue cleanup")
        
        # Connect to Redis using same URL as Celery
        r = redis.from_url(redis_url)
        logger.debug(f"Connected to Redis at {redis_url}")
        
        # Get all celery keys
        celery_keys = r.keys('celery-task-meta-*')
        
        if celery_keys:
            logger.info(f"Found {len(celery_keys)} celery task results in Redis")
            
            # Check each key and remove expired ones manually if needed
            expired_count = 0
            for key in celery_keys:
                ttl = r.ttl(key)
                if ttl == -1:  # No expiration set
                    # Set expiration to 1 hour from now
                    r.expire(key, 3600)
                    expired_count += 1
            
            logger.info(f"Set expiration on {expired_count} keys without TTL")
        else:
            logger.info("No Celery task keys found in Redis")
        
        # Also clean up any failed/revoked task keys
        failed_keys = r.keys('celery-task-meta-*') + r.keys('_kombu.binding.*')
        logger.debug(f"Total Redis keys related to Celery: {len(failed_keys)}")
        
        logger.info("Redis queue cleanup completed successfully")
        return {
            "status": "success",
            "celery_keys": len(celery_keys),
            "expired_set": expired_count
        }
        
    except Exception as e:
        logger.error(f"Redis cleanup error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}

@celery_app.task(bind=True)
def process_batch_upload(self, batch_id: str, files_data: List[Dict], user_id: str = None):
    """
    Process a batch of uploaded files in the background.
    
    This Celery task processes each file in the batch, updating the progress
    in the database as it goes. It handles errors for individual files without
    failing the entire batch.
    
    Args:
        batch_id (str): Unique batch identifier
        files_data (List[Dict]): List of file information (filename and base64 content)
        user_id (str): Optional user ID to associate with the uploads
        
    Returns:
        dict: Processing results including success/failure counts
    """
    try:
        logger.info(f"Starting batch processing for batch_id: {batch_id}")
        logger.info(f"Processing {len(files_data)} files for user: {user_id}")
        
        total_files = len(files_data)
        processed_files = 0
        failed_files = 0
        results = []
        
        # Update batch status to processing
        logger.info(f"Updating batch status to processing: {batch_id}")
        update_batch_progress(batch_id, processed_files, total_files, "processing")
        logger.debug(f"Batch status updated successfully: {batch_id}")
        
        for i, file_info in enumerate(files_data):
            try:
                filename = file_info.get('filename', 'unknown')
                logger.info(f"Processing file {i+1}/{total_files}: {filename}")
                
                # Update task progress
                progress_data = {
                    'batch_id': batch_id,
                    'current': processed_files,
                    'total': total_files,
                    'processing_file': filename
                }
                logger.debug(f"Updating Celery task state: {progress_data}")
                self.update_state(
                    state='PROGRESS',
                    meta=progress_data
                )
                
                # Process individual file
                logger.debug(f"Calling process_single_file for {filename}")
                result = process_single_file(file_info, batch_id, user_id)
                results.append(result)
                
                if result['success']:
                    processed_files += 1
                    logger.info(f"File {i+1}/{total_files} processed successfully: {filename}")
                else:
                    failed_files += 1
                    logger.warning(f"File {i+1}/{total_files} failed: {filename}, error: {result.get('error', 'Unknown error')}")
                    
                # Update batch progress in database
                logger.debug(f"Updating batch progress: {batch_id}, processed: {processed_files}/{total_files}")
                update_batch_progress(batch_id, processed_files, total_files, "processing")
                
            except Exception as file_error:
                logger.error(f"Critical error processing file {i+1}/{total_files} ({filename}): {file_error}")
                import traceback
                logger.error(traceback.format_exc())
                failed_files += 1
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': str(file_error)
                })
        
        # Final status update
        final_status = "completed" if failed_files == 0 else "completed_with_errors"
        logger.info(f"Finalizing batch {batch_id} with status: {final_status}")
        update_batch_progress(batch_id, processed_files, total_files, final_status)
        
        logger.info(f"Batch processing completed: {batch_id}")
        logger.info(f"Results: {processed_files}/{total_files} files processed successfully, {failed_files} failed")
        
        return {
            'batch_id': batch_id,
            'status': final_status,
            'total_files': total_files,
            'processed_files': processed_files,
            'failed_files': failed_files,
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Critical batch processing error for batch {batch_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        update_batch_progress(batch_id, processed_files, total_files, "failed")
        raise e

def process_single_file(file_info: Dict, batch_id: str, user_id: str = None) -> Dict:
    """
    Process a single file from the batch.
    
    This function handles the complete processing pipeline for a single file:
    1. Decode base64 content
    2. Create temporary file
    3. Detect file type
    4. Convert to DICOM if needed
    5. Anonymize DICOM
    6. Encrypt file
    7. Save records to database
    8. Clean up temporary files
    
    Args:
        file_info (Dict): Dictionary containing file information (filename and base64 content)
        batch_id (str): The batch ID this file belongs to
        user_id (str, optional): User ID to associate with the upload
        
    Returns:
        Dict: Processing result with success status and file details
    """
    filename = "unknown"
    try:
        filename = file_info.get('filename', 'unknown')
        file_content = file_info.get('content')  # Base64 encoded content
        
        logger.info(f"Processing file: {filename}")
        
        if not file_content:
            logger.error(f"File content missing for {filename}")
            raise ValueError("File content is missing from file_info")
        
        # Decode file content
        import base64
        logger.debug(f"Decoding base64 content for {filename}")
        file_bytes = base64.b64decode(file_content)
        logger.debug(f"File decoded, size: {len(file_bytes)} bytes")
        
        # Generate upload ID
        upload_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[-1].lower()
        now = datetime.utcnow()
        logger.debug(f"Generated upload ID: {upload_id} for {filename}")
        
        # Create temporary file
        logger.debug(f"Creating temporary file for {filename}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name
        logger.debug(f"Temporary file created: {temp_path}")
        
        try:
            # Detect file type
            logger.info(f"Detecting file type for {filename}")
            file_type = detect_file_type(file_bytes, filename)
            logger.info(f"File type detected: {file_type}")
            
            # Calculate hash
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            logger.debug(f"File hash: {sha256_hash}")
            
            if file_type == 'dicom':
                logger.info(f"Processing existing DICOM file: {filename}")
                # Handle existing DICOM files
                dicom_path = temp_path
                # Still anonymize existing DICOM
                logger.info(f"Anonymizing existing DICOM file: {filename}")
                anonymized_path, removed_tags = anonymize_dicom(dicom_path)
                logger.debug(f"Anonymization complete, removed {len(removed_tags)} tags")
            else:
                logger.info(f"Converting image to DICOM: {filename}")
                # Convert image to DICOM
                dicom_path = convert_to_dicom(temp_path, upload_id)
                logger.debug(f"Conversion complete: {dicom_path}")
                
                # Anonymize converted DICOM
                logger.info(f"Anonymizing converted DICOM file: {filename}")
                anonymized_path, removed_tags = anonymize_dicom(dicom_path)
                logger.debug(f"Anonymization complete, removed {len(removed_tags)} tags")
            
            logger.info(f"Encrypting file: {filename}")
            # Encrypt the anonymized file
            encrypted_path = encrypt_file(anonymized_path)
            logger.debug(f"Encryption complete: {encrypted_path}")
            
            logger.info(f"Saving to database: {filename}, upload_id={upload_id}")
            # Save to database
            save_upload_record(upload_id, filename, ext, now, "batch_upload", encrypted_path, sha256_hash, batch_id)
            save_dicom_metadata(upload_id, True, True, removed_tags, now)
            
            # Mock ML result (replace with actual AI model)
            logger.info(f"Running ML analysis on file: {filename}")
            diagnosis, confidence = "Processing Complete", 0.95
            save_ml_result(upload_id, "v1.0", diagnosis, confidence, now)
            logger.debug(f"ML analysis complete: diagnosis={diagnosis}, confidence={confidence}")
            
            # Save user upload association
            if user_id:
                logger.info(f"Associating upload with user: user_id={user_id}, upload_id={upload_id}")
                save_user_upload(user_id, upload_id, now)
            
            # Audit log
            logger.debug(f"Saving audit log for {filename}, upload_id={upload_id}")
            save_audit_log(upload_id, "batch_processed", now, "batch_upload", "success", {
                "batch_id": batch_id,
                "file_type": file_type
            })
            
            logger.info(f"File {filename} processed successfully!")
            
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
                    logger.debug(f"Cleaned up temporary file: {temp_path}")
            except Exception as cleanup_error:
                logger.warning(f"Could not clean up temp file {temp_path}: {cleanup_error}")
                
    except Exception as e:
        logger.error(f"Critical error processing file {filename}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'filename': filename,
            'success': False,
            'error': str(e)
        }
