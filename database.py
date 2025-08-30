import psycopg2
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from contextlib import contextmanager

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
    if DB_CONFIG['db_url']:
        conn = psycopg2.connect(DB_CONFIG['db_url'], sslmode='require')
    else:
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
except Exception as e:
    print(f"Warning: Could not establish global database connection: {e}")
    conn = None
    cur = None

def save_upload_record(upload_id, filename, ext, upload_time, ip, storage_path, sha256_hash, batch_id=None):
    try:
        cur.execute("""
            INSERT INTO public.uploads (id, original_filename, file_type, upload_time, uploader_ip, storage_path, sha256_hash, encrypted, status, batch_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, 'processed', %s)
        """, (upload_id, filename, ext, upload_time, ip, storage_path, sha256_hash, batch_id))
        return True
    except Exception as e:
        print(f"Error saving upload record: {e}")
        return False

def save_batch_record(batch_id, user_id, total_files, status="queued"):
    """Save batch upload record"""
    try:
        cur.execute("""
            INSERT INTO public.upload_batches (batch_id, user_id, total_files, processed_files, status, created_at)
            VALUES (%s, %s, %s, 0, %s, %s)
        """, (batch_id, user_id, total_files, status, datetime.utcnow()))
        return True
    except Exception as e:
        print(f"Error saving batch record: {e}")
        return False

def update_batch_progress(batch_id, processed_files, total_files, status):
    """Update batch processing progress with fresh database connection"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.upload_batches 
                    SET processed_files = %s, status = %s, updated_at = %s
                    WHERE batch_id = %s
                """, (processed_files, status, datetime.utcnow(), batch_id))
                return True
    except Exception as e:
        print(f"Error updating batch progress: {e}")
        return False

def get_batch_status(batch_id):
    """Get batch processing status with fresh database connection"""
    try:
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
                    return dict(zip(columns, result))
                return None
    except Exception as e:
        print(f"Error getting batch status: {e}")
        return None

def get_user_batches(user_id):
    """Get all batches for a user with fresh database connection"""
    try:
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
                return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        print(f"Error getting user batches: {e}")
        return []

def save_dicom_metadata(upload_id, dicom_converted, anonymized, removed_tags, processed_at):
    cur.execute("""
        INSERT INTO public.dicom_metadata (upload_id, dicom_converted, anonymized, removed_tags, processed_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (upload_id, dicom_converted, anonymized, json.dumps(removed_tags), processed_at))

def save_ml_result(upload_id, model_version, diagnosis, confidence, analyzed_at):
    cur.execute("""
        INSERT INTO public.ml_results (upload_id, model_version, diagnosis, confidence_score, analyzed_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (upload_id, model_version, diagnosis, confidence, analyzed_at))

def save_audit_log(upload_id, action, timestamp, ip, status, details):
    cur.execute("""
        INSERT INTO public.audit_log (upload_id, action, timestamp, ip_address, status, details)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (upload_id, action, timestamp, ip, status, json.dumps(details)))


# Generic user upload save (not Wix-specific)
def save_user_upload(user_id, upload_id, upload_time):
    """
    Save upload data to user_uploads table
    Args:
        user_id (str): The user ID from your frontend
        upload_id (str): The upload ID generated by your service
        upload_time (datetime): The time of upload
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        cur.execute("""
            INSERT INTO public.user_uploads (user_id, upload_id, upload_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, upload_id) DO UPDATE SET
                upload_time = EXCLUDED.upload_time,
                created_at = CURRENT_TIMESTAMP
        """, (user_id, upload_id, upload_time))
        return True
    except Exception as e:
        print(f"Error saving to user_uploads: {e}")
        return False

def get_user_uploads(user_id):
    """
    Get all uploads for a specific user with fresh database connection
    
    Args:
        user_id (str): The user ID to search for
        
    Returns:
        list: List of upload records for the user
    """
    try:
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
                
                return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        print(f"Error getting user uploads: {e}")
        return []

def get_upload_by_id(upload_id):
    """
    Get upload data by upload ID with fresh database connection
    
    Args:
        upload_id (str): The upload ID to search for
        
    Returns:
        dict: Upload data or None if not found
    """
    try:
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
                    return dict(zip(columns, result))
                return None
    except Exception as e:
        print(f"Error getting upload by ID: {e}")
        return None


# Generic upload stats (not Wix-specific)
def get_upload_stats():
    """
    Get statistics about user uploads
    Returns:
        dict: Statistics about uploads
    """
    try:
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
            return {
                "total_uploads": result[0],
                "unique_users": result[1],
                "latest_upload": result[2].isoformat() if result[2] else None,
                "earliest_upload": result[3].isoformat() if result[3] else None
            }
        return {"total_uploads": 0, "unique_users": 0, "latest_upload": None, "earliest_upload": None}
    except Exception as e:
        print(f"Error getting upload stats: {e}")
        return {"error": str(e)}
