#!/usr/bin/env python3
"""
Render-optimized DICOM service entry point
Runs FastAPI + Celery worker in single container for free tier
"""

import os
import sys
import threading
import time
import signal
from contextlib import asynccontextmanager

# Set environment variables for production
os.environ.setdefault('CELERY_BROKER_URL', os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
os.environ.setdefault('CELERY_RESULT_BACKEND', os.getenv('REDIS_URL', 'redis://localhost:6379/0'))

def start_celery_worker():
    """Start Celery worker in background thread"""
    try:
        print("Starting Celery worker...")
        from job_queue import celery_app
        
        # Start worker optimized for free tier
        celery_app.worker_main([
            'worker',
            '--loglevel=info',
            '--pool=solo',  # Single-threaded
            '--concurrency=1',
            '--without-gossip',
            '--without-mingle', 
            '--without-heartbeat',
            '--max-tasks-per-child=50',  # Restart worker frequently
        ])
    except Exception as e:
        print(f"Celery worker error: {e}")

@asynccontextmanager
async def lifespan(app):
    """Manage application lifecycle"""
    # Start Celery worker in background
    worker_thread = threading.Thread(target=start_celery_worker, daemon=True)
    worker_thread.start()
    
    print("DICOM Service started with background worker")
    yield
    print("DICOM Service shutting down")

# Import FastAPI app
from main import app

# Update the app to include lifespan management
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting server on port {port}")
    print(f"Redis URL: {os.getenv('REDIS_URL', 'Not set')}")
    print(f"Database URL: {os.getenv('DATABASE_URL', 'Not set')[:50]}...")
    
    uvicorn.run(
        "app_render:app",
        host="0.0.0.0",
        port=port,
        access_log=True,
        log_level="info"
    )
