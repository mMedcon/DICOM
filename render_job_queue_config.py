"""
Render-optimized job queue configuration for free tier deployment
Use this configuration when deploying to Render
"""

import os
from celery import Celery

# Get Redis URL from environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery
celery_app = Celery(
    'dicom_processor',
    broker=redis_url,
    backend=redis_url
)

# Render free tier optimized configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    # Shorter timeouts for free tier
    task_time_limit=10 * 60,  # 10 minutes max per task (free tier limit)
    task_soft_time_limit=8 * 60,  # 8 minutes soft limit
    worker_prefetch_multiplier=1,
    # Free tier settings
    worker_pool='solo',  # Single-threaded for consistency
    task_always_eager=False,
    # Aggressive cleanup for limited Redis memory
    result_expires=1800,  # Results expire after 30 minutes (not 1 hour)
    task_ignore_result=True,  # Don't store results for simple tasks
    # Memory management
    worker_max_tasks_per_child=20,  # Restart worker more frequently
    task_acks_late=True,
    worker_disable_rate_limits=True,
    # Reduce Redis memory footprint
    result_compression='zlib',  # Compress results
    task_compression='zlib',   # Compress task data
    # Connection reliability
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
)

def get_queue_stats():
    """Get current queue statistics"""
    try:
        import redis
        r = redis.from_url(redis_url)
        
        # Get basic Redis info
        info = r.info()
        memory_used = info.get('used_memory_human', 'Unknown')
        
        # Get Celery-specific keys
        celery_keys = r.keys('celery-task-meta-*')
        
        return {
            "redis_memory": memory_used,
            "task_results": len(celery_keys),
            "redis_keys_total": r.dbsize()
        }
    except Exception as e:
        return {"error": str(e)}
