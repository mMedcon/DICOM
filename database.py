import psycopg2
import json
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from contextlib import contextmanager

# Get logger
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Database connection configuration
DB_CONFIG = {
    'db_url': os.getenv("DATABASE_URL"),
    'dbname': os.getenv("POSTGRES_DB"),
    'user': os.getenv("POSTGRES_USER"),
    'password': os.getenv("POSTGRES_PASSWORD"),
    'host': os.getenv("POSTGRES_HOST"),
    'port': os.getenv("POSTGRES_PORT"),
}

@contextmanager
def get_db_connection():
    """Context manager for database connections to ensure they're properly closed"""
    conn = None
    try:
        if DB_CONFIG['db_url']:
            # Render provides DATABASE_URL
            conn = psycopg2.connect(DB_CONFIG['db_url'], sslmode='require')
        else:
            # Local development
            conn = psycopg2.connect(
                dbname=DB_CONFIG['dbname'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                host=DB_CONFIG['host'],
                port=DB_CONFIG['port'],
                connect_timeout=5,
                application_name="DICOM_Service"
            )
        
        conn.autocommit = True
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

# Legacy global connection for backwards compatibility (will be phased out)
try:
    logger.info("Establishing global database connection for legacy compatibility")
    if DB_CONFIG['db_url']:
        logger.debug("Using DATABASE_URL for connection")
        conn = psycopg2.connect(DB_CONFIG['db_url'], sslmode='require')
    else:
        logger.debug("Using individual connection parameters")
        conn = psycopg2.connect(
            dbname=DB_CONFIG['dbname'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            connect_timeout=5,
            application_name="DICOM_Service"
        )
    conn.autocommit = True
    cur = conn.cursor()
    logger.info("Global database connection established successfully")
except Exception as e:
    logger.warning(f"Could not establish global database connection: {e}")
    logger.warning("Database operations using global connection will fail")
    conn = None
    cur = None

def save_upload_record(upload_id, filename, ext, upload_time, ip, storage_path, sha256_hash, batch_id=None):
    """
    Save a new upload record to the database.
    
    Args:
        upload_id: Unique identifier for the upload
        filename: Original filename
        ext: File extension
        upload_time: Time of upload
        ip: IP address of uploader
        storage_path: Path where file is stored
        sha256_hash: SHA256 hash of file content
        batch_id: Optional batch ID if part of a batch
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.debug(f"Saving upload record: id={upload_id}, filename={filename}")
        cur.execute("""
            INSERT INTO public.uploads (id, original_filename, file_type, upload_time, uploader_ip, storage_path, sha256_hash, encrypted, status, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, 'processed', %s)
        """, (upload_id, filename, ext, upload_time, ip, storage_path, sha256_hash, batch_id))
        logger.debug(f"Upload record saved successfully: {upload_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving upload record: {e}")
        return False

def save_batch_record(batch_id, user_id, total_files, status="queued"):
    """
    Save a new batch upload record to the database.
    
    Args:
        batch_id: Unique identifier for the batch
        user_id: User ID associated with the batch
        total_files: Total number of files in the batch
        status: Initial status of the batch (default: queued)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.debug(f"Saving batch record: id={batch_id}, user_id={user_id}, files={total_files}")
        cur.execute("""
            INSERT INTO public.upload_batches (batch_id, user_id, total_files, processed_files, status, created_at)
            VALUES (%s, %s, %s, 0, %s, %s)
        """, (batch_id, user_id, total_files, status, datetime.utcnow()))
        logger.debug(f"Batch record saved successfully: {batch_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving batch record: {e}")
        return False

def update_batch_progress(batch_id, processed_files, total_files, status):
    """
    Update batch processing progress with fresh database connection.
    
    Args:
        batch_id: Unique identifier for the batch
        processed_files: Number of files processed so far
        total_files: Total number of files in the batch
        status: Current status of the batch
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.debug(f"Updating batch progress: id={batch_id}, processed={processed_files}/{total_files}, status={status}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.upload_batches 
                    SET processed_files = %s, status = %s, updated_at = %s
                    WHERE batch_id = %s
                """, (processed_files, status, datetime.utcnow(), batch_id))
                logger.debug(f"Batch progress updated successfully: {batch_id}")
                return True
    except Exception as e:
        logger.error(f"Error updating batch progress: {e}")
        return False

def get_batch_status(batch_id):
    """
    Get batch processing status with fresh database connection.
    
    Args:
        batch_id: Unique identifier for the batch
        
    Returns:
        dict: Batch status information or None if not found
    """
    try:
        logger.debug(f"Getting status for batch: {batch_id}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT batch_id, user_id, total_files, processed_files, status, created_at, updated_at
                    FROM public.upload_batches 
                    WHERE batch_id = %s
                """, (batch_id,))
                
                result = cur.fetchone()
                if result:
                    columns = [desc[0] for desc in cur.description]
                    batch_info = dict(zip(columns, result))
                    logger.debug(f"Found batch: {batch_id}, status={batch_info['status']}, processed={batch_info['processed_files']}/{batch_info['total_files']}")
                    return batch_info
                logger.warning(f"Batch not found: {batch_id}")
                return None
    except Exception as e:
        logger.error(f"Error getting batch status: {e}")
        return None

def get_user_batches(user_id):
    """
    Get all batches for a user with fresh database connection.
    
    Args:
        user_id: User ID to retrieve batches for
        
    Returns:
        list: List of batch records for the user
    """
    try:
        logger.debug(f"Getting batches for user: {user_id}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT batch_id, total_files, processed_files, status, created_at, updated_at
                    FROM public.upload_batches 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                """, (user_id,))
                
                columns = [desc[0] for desc in cur.description]
                results = cur.fetchall()
                batches = [dict(zip(columns, row)) for row in results]
                logger.debug(f"Found {len(batches)} batches for user: {user_id}")
                return batches
    except Exception as e:
        logger.error(f"Error getting user batches: {e}")
        return []

def save_dicom_metadata(upload_id, dicom_converted, anonymized, removed_tags, processed_at):
    """
    Save DICOM metadata for an upload.
    
    Args:
        upload_id: Unique identifier for the upload
        dicom_converted: Whether the file was converted to DICOM
        anonymized: Whether the DICOM file was anonymized
        removed_tags: List of tags removed during anonymization
        processed_at: Time of processing
    """
    try:
        logger.debug(f"Saving DICOM metadata for upload: {upload_id}")
        cur.execute("""
            INSERT INTO public.dicom_metadata (upload_id, dicom_converted, anonymized, removed_tags, processed_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (upload_id, dicom_converted, anonymized, json.dumps(removed_tags), processed_at))
        logger.debug(f"DICOM metadata saved successfully: {upload_id}")
    except Exception as e:
        logger.error(f"Error saving DICOM metadata: {e}")

def save_ml_result(upload_id, model_version, diagnosis, confidence, analyzed_at):
    """
    Save machine learning analysis result for an upload.
    
    Args:
        upload_id: Unique identifier for the upload
        model_version: Version of the ML model used
        diagnosis: Diagnosis result from the ML model
        confidence: Confidence score of the diagnosis
        analyzed_at: Time of analysis
    """
    try:
        logger.debug(f"Saving ML result for upload: {upload_id}")
        cur.execute("""
            INSERT INTO public.ml_results (upload_id, model_version, diagnosis, confidence_score, analyzed_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (upload_id, model_version, diagnosis, confidence, analyzed_at))
        logger.debug(f"ML result saved successfully: {upload_id}, diagnosis={diagnosis}, confidence={confidence}")
    except Exception as e:
        logger.error(f"Error saving ML result: {e}")

def save_audit_log(upload_id, action, timestamp, ip, status, details):
    """
    Save an audit log entry.
    
    Args:
        upload_id: Unique identifier for the upload (can be None)
        action: Action being audited
        timestamp: Time of the action
        ip: IP address associated with the action
        status: Status of the action (success, error, etc.)
        details: Additional details about the action
    """
    try:
        logger.debug(f"Saving audit log: upload_id={upload_id}, action={action}, status={status}")
        cur.execute("""
            INSERT INTO public.audit_log (upload_id, action, timestamp, ip_address, status, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (upload_id, action, timestamp, ip, status, json.dumps(details)))
        logger.debug(f"Audit log saved successfully")
    except Exception as e:
        logger.error(f"Error saving audit log: {e}")


# Generic user upload save (not Wix-specific)
def save_user_upload(user_id, upload_id, upload_time):
    """
    Save upload data to user_uploads table.
    
    Associates an upload with a specific user in the database.
    
    Args:
        user_id (str): The user ID from your frontend
        upload_id (str): The upload ID generated by your service
        upload_time (datetime): The time of upload
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.debug(f"Associating upload with user: user_id={user_id}, upload_id={upload_id}")
        cur.execute("""
            INSERT INTO public.user_uploads (user_id, upload_id, upload_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, upload_id) DO UPDATE SET
                upload_time = EXCLUDED.upload_time,
                created_at = CURRENT_TIMESTAMP
        """, (user_id, upload_id, upload_time))
        logger.debug(f"User upload association saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving to user_uploads: {e}")
        return False

def get_user_uploads(user_id):
    """
    Get all uploads for a specific user with fresh database connection.
    
    Retrieves all uploads associated with a user, including file details
    and ML results, ordered by upload time.
    
    Args:
        user_id (str): The user ID to search for
        
    Returns:
        list: List of upload records for the user
    """
    try:
        logger.debug(f"Getting uploads for user: {user_id}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        uu.user_id,
                        uu.upload_id,
                        uu.upload_time,
                        u.original_filename,
                        u.file_type,
                        u.status,
                        u.upload_time as file_upload_time,
                        ml.diagnosis,
                        ml.confidence_score
                    FROM public.user_uploads uu
                    LEFT JOIN public.uploads u ON uu.upload_id = u.id
                    LEFT JOIN public.ml_results ml ON uu.upload_id = ml.upload_id
                    WHERE uu.user_id = %s
                    ORDER BY uu.upload_time DESC
                """, (user_id,))
                
                columns = [desc[0] for desc in cur.description]
                results = cur.fetchall()
                uploads = [dict(zip(columns, row)) for row in results]
                
                logger.debug(f"Found {len(uploads)} uploads for user: {user_id}")
                return uploads
    except Exception as e:
        logger.error(f"Error getting user uploads: {e}")
        return []

def get_upload_by_id(upload_id):
    """
    Get upload data by upload ID with fresh database connection.
    
    Retrieves detailed information about a specific upload, including
    file details and ML results.
    
    Args:
        upload_id (str): The upload ID to search for
        
    Returns:
        dict: Upload data or None if not found
    """
    try:
        logger.debug(f"Getting upload details by ID: {upload_id}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        uu.user_id,
                        uu.upload_id,
                        uu.upload_time,
                        u.original_filename,
                        u.file_type,
                        u.status,
                        u.uploader_ip,
                        u.upload_time as file_upload_time,
                        ml.diagnosis,
                        ml.confidence_score
                    FROM public.user_uploads uu
                    LEFT JOIN public.uploads u ON uu.upload_id = u.id
                    LEFT JOIN public.ml_results ml ON uu.upload_id = ml.upload_id
                    WHERE uu.upload_id = %s
                """, (upload_id,))
                
                result = cur.fetchone()
                if result:
                    columns = [desc[0] for desc in cur.description]
                    upload_data = dict(zip(columns, result))
                    logger.debug(f"Found upload: {upload_id}, filename={upload_data.get('original_filename')}")
                    return upload_data
                
                logger.warning(f"Upload not found: {upload_id}")
                return None
    except Exception as e:
        logger.error(f"Error getting upload by ID: {e}")
        return None


# Generic upload stats (not Wix-specific)
def get_all_uploads():
    """
    Get all uploads with their associated user IDs with fresh database connection.
    
    Retrieves all uploads from the database, including file details, user IDs,
    and ML results, ordered by upload time.
    
    Returns:
        list: List of all upload records with their user IDs
    """
    try:
        logger.debug("Getting all uploads with user IDs")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        uu.user_id,
                        uu.upload_id,
                        uu.upload_time,
                        u.original_filename,
                        u.file_type,
                        u.status,
                        u.upload_time as file_upload_time,
                        ml.diagnosis,
                        ml.confidence_score
                    FROM public.user_uploads uu
                    LEFT JOIN public.uploads u ON uu.upload_id = u.id
                    LEFT JOIN public.ml_results ml ON uu.upload_id = ml.upload_id
                    ORDER BY uu.upload_time DESC
                """)
                
                columns = [desc[0] for desc in cur.description]
                results = cur.fetchall()
                uploads = [dict(zip(columns, row)) for row in results]
                
                logger.debug(f"Found {len(uploads)} total uploads")
                return uploads
    except Exception as e:
        logger.error(f"Error getting all uploads: {e}")
        return []

def get_upload_stats():
    """
    Get statistics about user uploads.
    
    Retrieves aggregate statistics about uploads in the system,
    including total count, unique users, and timestamp ranges.
    
    Returns:
        dict: Statistics about uploads
    """
    try:
        logger.debug("Getting upload statistics")
        cur.execute("""
            SELECT 
                COUNT(*) as total_uploads,
                COUNT(DISTINCT user_id) as unique_users,
                MAX(upload_time) as latest_upload,
                MIN(upload_time) as earliest_upload
            FROM public.user_uploads
        """)
        result = cur.fetchone()
        if result:
            stats = {
                "total_uploads": result[0],
                "unique_users": result[1],
                "latest_upload": result[2].isoformat() if result[2] else None,
                "earliest_upload": result[3].isoformat() if result[3] else None
            }
            logger.debug(f"Upload statistics: {stats['total_uploads']} uploads, {stats['unique_users']} users")
            return stats
        
        logger.debug("No upload statistics found")
        return {"total_uploads": 0, "unique_users": 0, "latest_upload": None, "earliest_upload": None}
    except Exception as e:
        logger.error(f"Error getting upload stats: {e}")
        return {"error": str(e)}
