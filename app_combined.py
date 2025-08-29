"""
Combined FastAPI + Celery application for Render free tier deployment
Runs both web server and celery worker in the same process
"""

import os
import sys
import threading
import time
import multiprocessing
from job_queue import celery_app

def start_celery_worker():
    """Start Celery worker in a separate thread"""
    print("Starting Celery worker thread...")
    try:
        # Start worker with minimal concurrency for free tier
        celery_app.worker_main([
            'worker',
            '--loglevel=info',
            '--pool=solo',  # Single-threaded pool for free tier
            '--concurrency=1',  # Only 1 worker
            '--without-gossip',  # Reduce overhead
            '--without-mingle',  # Reduce overhead
            '--without-heartbeat',  # Reduce overhead
        ])
    except Exception as e:
        print(f"Celery worker failed: {e}")

def start_web_server():
    """Start FastAPI web server"""
    import uvicorn
    from main import app
    
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting FastAPI server on port {port}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        access_log=True,
        loop="asyncio"
    )

if __name__ == "__main__":
    print("Starting combined DICOM service...")
    
    # Start Celery worker in a separate thread
    worker_thread = threading.Thread(target=start_celery_worker, daemon=True)
    worker_thread.start()
    
    # Give worker time to start
    time.sleep(2)
    
    # Start web server (this will block)
    start_web_server()