#!/usr/bin/env python3
"""
Celery worker script for processing DICOM batch uploads
Run this in a separate terminal: python celery_worker.py
"""

from job_queue import celery_app

if __name__ == '__main__':
    print("Starting Celery worker for DICOM batch processing...")
    celery_app.start(['celery', 'worker', '--loglevel=info', '--concurrency=4'])
