#!/usr/bin/env python3
"""
Windows-compatible Celery worker script for DICOM batch processing
Run this instead of the regular celery command on Windows
"""

import os
import sys

# Set Windows-specific environment variables
os.environ['FORKED_BY_MULTIPROCESSING'] = '1'
os.environ['CELERY_OPTIMIZATION'] = 'fair'

# Import after setting environment variables
from job_queue import celery_app

if __name__ == '__main__':
    print("Starting Windows-compatible Celery worker for DICOM batch processing...")
    print("Using 'solo' pool (single-threaded) for Windows compatibility")
    print("Worker configuration:")
    print("   - Pool: solo (Windows-compatible)")
    print("   - Concurrency: 1 (single-threaded)")
    print("   - Broker: Redis")
    print("   - Backend: Redis")
    print("=" * 60)
    
    # Start worker with Windows-compatible settings
    celery_app.worker_main([
        'worker',
        '--loglevel=info',
        '--pool=solo',  # Solo pool for Windows
        '--concurrency=1',  # Single process
        '--without-gossip',  # Disable gossip for Windows
        '--without-mingle',  # Disable mingle for Windows
        '--without-heartbeat',  # Disable heartbeat for Windows
    ])
