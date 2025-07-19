CREATE TABLE uploads (
    id UUID PRIMARY KEY,
    original_filename TEXT,
    file_type TEXT,
    upload_time TIMESTAMP,
    uploader_ip TEXT,
    storage_path TEXT,
    sha256_hash TEXT,
    encrypted BOOLEAN,
    status TEXT
);

CREATE TABLE dicom_metadata (
    upload_id UUID REFERENCES uploads(id),
    dicom_converted BOOLEAN,
    anonymized BOOLEAN,
    removed_tags JSONB,
    processed_at TIMESTAMP
);

CREATE TABLE ml_results (
    upload_id UUID REFERENCES uploads(id),
    model_version TEXT,
    diagnosis TEXT,
    confidence_score DECIMAL,
    analyzed_at TIMESTAMP
);

CREATE TABLE audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    upload_id UUID,
    action TEXT,
    timestamp TIMESTAMP,
    ip_address TEXT,
    status TEXT,
    details JSONB
);
