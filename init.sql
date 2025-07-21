CREATE TABLE public.uploads (
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

CREATE TABLE public.dicom_metadata (
    upload_id UUID REFERENCES public.uploads(id),
    dicom_converted BOOLEAN,
    anonymized BOOLEAN,
    removed_tags JSONB,
    processed_at TIMESTAMP
);

CREATE TABLE public.ml_results (
    upload_id UUID REFERENCES public.uploads(id),
    model_version TEXT,
    diagnosis TEXT,
    confidence_score DECIMAL,
    analyzed_at TIMESTAMP
);

CREATE TABLE public.audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    upload_id UUID,
    action TEXT,
    timestamp TIMESTAMP,
    ip_address TEXT,
    status TEXT,
    details JSONB
);

-- New table for Wix uploads collection data
CREATE TABLE public.wix_uploads (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    upload_id UUID NOT NULL REFERENCES public.uploads(id),
    upload_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, upload_id)
);

-- Index for faster queries
CREATE INDEX idx_wix_uploads_user_id ON public.wix_uploads(user_id);
CREATE INDEX idx_wix_uploads_upload_id ON public.wix_uploads(upload_id);
CREATE INDEX idx_wix_uploads_time ON public.wix_uploads(upload_time);
