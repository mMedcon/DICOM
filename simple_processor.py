"""
Simple background processor for batch uploads (Windows-friendly alternative)
This processes batches without Celery to avoid Windows multiprocessing issues
"""

import time
import threading
import json
import logging
from typing import Dict, List
from queue import Queue
from job_queue import process_single_file
from database import update_batch_progress, get_batch_status

# Get logger
logger = logging.getLogger(__name__)

# Global queue for batch processing
batch_queue = Queue()
processing_thread = None
is_processing = False

def start_background_processor():
    """
    Start the background processing thread.
    
    This function initializes and starts a daemon thread that will
    process batches from the queue in the background. If a thread
    is already running, it won't start a new one.
    """
    global processing_thread, is_processing
    
    if processing_thread is None or not processing_thread.is_alive():
        logger.info("Starting background batch processor")
        is_processing = True
        processing_thread = threading.Thread(target=batch_processor_worker, daemon=True)
        processing_thread.start()
        logger.info("Background batch processor thread started")
    else:
        logger.debug("Background processor already running, not starting a new one")

def batch_processor_worker():
    """
    Worker thread that processes batches from the queue.
    
    This function runs in a background thread and continuously checks
    the queue for new batches to process. When a batch is found, it
    processes it and then continues checking for more.
    """
    global is_processing
    
    logger.info("Background processor worker thread started")
    
    while is_processing:
        try:
            if not batch_queue.empty():
                # Get batch from queue
                batch_data = batch_queue.get(timeout=1)
                batch_id = batch_data['batch_id']
                logger.info(f"Processing batch from queue: {batch_id}")
                
                # Process the batch
                process_batch_sync(
                    batch_id,
                    batch_data['files_data'],
                    batch_data.get('user_id')
                )
                
                batch_queue.task_done()
                logger.debug(f"Batch {batch_id} processing complete, task marked as done")
            else:
                # No work available, sleep briefly
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in batch processor worker: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.info("Worker will retry after 5 seconds")
            time.sleep(5)  # Wait before retrying

def process_batch_sync(batch_id: str, files_data: List[Dict], user_id: str = None):
    """
    Synchronously process a batch (runs in background thread).
    
    This function processes each file in the batch sequentially,
    updating the progress in the database as it goes. It handles
    errors for individual files without failing the entire batch.
    
    Args:
        batch_id (str): Unique batch identifier
        files_data (List[Dict]): List of file information (filename and base64 content)
        user_id (str, optional): User ID to associate with the uploads
        
    Returns:
        dict: Processing results including success/failure counts
    """
    try:
        logger.info(f"Starting batch processing for batch_id: {batch_id}")
        logger.info(f"Processing {len(files_data)} files for user: {user_id}")
        
        total_files = len(files_data)
        processed_files = 0
        failed_files = 0
        results = []
        
        # Update batch status to processing
        logger.info(f"Updating batch status to processing: {batch_id}")
        update_batch_progress(batch_id, processed_files, total_files, "processing")
        logger.debug(f"Batch status updated successfully: {batch_id}")
        
        for i, file_info in enumerate(files_data):
            try:
                filename = file_info.get('filename', 'unknown')
                logger.info(f"Processing file {i+1}/{total_files}: {filename}")
                
                # Process individual file
                result = process_single_file(file_info, batch_id, user_id)
                results.append(result)
                
                if result['success']:
                    processed_files += 1
                    logger.info(f"File {i+1}/{total_files} processed successfully: {filename}")
                else:
                    failed_files += 1
                    logger.warning(f"File {i+1}/{total_files} failed: {filename}, error: {result.get('error', 'Unknown error')}")
                    
                # Update batch progress in database
                logger.debug(f"Updating batch progress: {batch_id}, processed: {processed_files}/{total_files}")
                update_batch_progress(batch_id, processed_files, total_files, "processing")
                
            except Exception as file_error:
                filename = file_info.get('filename', 'unknown')
                logger.error(f"Critical error processing file {i+1}/{total_files} ({filename}): {file_error}")
                import traceback
                logger.error(traceback.format_exc())
                failed_files += 1
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': str(file_error)
                })
        
        # Final status update
        final_status = "completed" if failed_files == 0 else "completed_with_errors"
        logger.info(f"Finalizing batch {batch_id} with status: {final_status}")
        update_batch_progress(batch_id, processed_files, total_files, final_status)
        
        logger.info(f"Batch processing completed: {batch_id}")
        logger.info(f"Results: {processed_files}/{total_files} files processed successfully, {failed_files} failed")
        
        return {
            'batch_id': batch_id,
            'status': final_status,
            'total_files': total_files,
            'processed_files': processed_files,
            'failed_files': failed_files,
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Critical batch processing error for batch {batch_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        update_batch_progress(batch_id, processed_files, total_files, "failed")

def queue_batch_for_processing(batch_id: str, files_data: List[Dict], user_id: str = None):
    """
    Queue a batch for background processing.
    
    This function adds a batch to the processing queue and ensures
    the background processor is running to handle it.
    
    Args:
        batch_id (str): Unique batch identifier
        files_data (List[Dict]): List of file information (filename and base64 content)
        user_id (str, optional): User ID to associate with the uploads
    """
    batch_data = {
        'batch_id': batch_id,
        'files_data': files_data,
        'user_id': user_id
    }
    
    logger.info(f"Queueing batch {batch_id} for processing with {len(files_data)} files")
    batch_queue.put(batch_data)
    logger.debug(f"Batch {batch_id} added to processing queue")
    
    # Start processor if not running
    logger.debug("Ensuring background processor is running")
    start_background_processor()

def stop_background_processor():
    """
    Stop the background processor.
    
    This function signals the background processor thread to stop
    after it finishes processing the current batch (if any).
    """
    global is_processing
    logger.info("Stopping background processor")
    is_processing = False
    logger.info("Background processor signaled to stop")
