import psycopg2
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "mmedconv2"),
    user=os.getenv("POSTGRES_USER", "dummy_user"),
    password=os.getenv("POSTGRES_PASSWORD", "dummy_password"),
    host=os.getenv("POSTGRES_HOST", "dummy_host"),
    port=os.getenv("POSTGRES_PORT", "5432")
)
conn.autocommit = True
cur = conn.cursor()

def save_upload_record(upload_id, filename, ext, upload_time, ip, storage_path, sha256_hash):
    cur.execute("""
        INSERT INTO uploads (id, original_filename, file_type, upload_time, uploader_ip, storage_path, sha256_hash, encrypted, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, 'processed')
    """, (upload_id, filename, ext, upload_time, ip, storage_path, sha256_hash))

def save_dicom_metadata(upload_id, dicom_converted, anonymized, removed_tags, processed_at):
    cur.execute("""
        INSERT INTO dicom_metadata (upload_id, dicom_converted, anonymized, removed_tags, processed_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (upload_id, dicom_converted, anonymized, json.dumps(removed_tags), processed_at))

def save_ml_result(upload_id, model_version, diagnosis, confidence, analyzed_at):
    cur.execute("""
        INSERT INTO ml_results (upload_id, model_version, diagnosis, confidence_score, analyzed_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (upload_id, model_version, diagnosis, confidence, analyzed_at))

def save_audit_log(upload_id, action, timestamp, ip, status, details):
    cur.execute("""
        INSERT INTO audit_log (upload_id, action, timestamp, ip_address, status, details)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (upload_id, action, timestamp, ip, status, json.dumps(details)))
