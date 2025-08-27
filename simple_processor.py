"""
Simple background processor for batch uploads (Windows-friendly alternative)
This processes batches without Celery to avoid Windows multiprocessing issues
"""

import time
import threading
import json
from typing import Dict, List
from queue import Queue
from job_queue import process_single_file
from database import update_batch_progress, get_batch_status

# Global queue for batch processing
batch_queue = Queue()
processing_thread = None
is_processing = False

def start_background_processor():
    """Start the background processing thread"""
    global processing_thread, is_processing
    
    if processing_thread is None or not processing_thread.is_alive():
        is_processing = True
        processing_thread = threading.Thread(target=batch_processor_worker, daemon=True)
        processing_thread.start()
        print("🚀 Background batch processor started")

def batch_processor_worker():
    """Worker thread that processes batches from the queue"""
    global is_processing
    
    print("🔄 Background processor worker started")
    
    while is_processing:
        try:
            if not batch_queue.empty():
                # Get batch from queue
                batch_data = batch_queue.get(timeout=1)
                print(f"📋 Processing batch: {batch_data['batch_id']}")
                
                # Process the batch
                process_batch_sync(
                    batch_data['batch_id'],
                    batch_data['files_data'],
                    batch_data.get('user_id')
                )
                
                batch_queue.task_done()
            else:
                # No work available, sleep briefly
                time.sleep(1)
                
        except Exception as e:
            print(f"💥 Error in batch processor worker: {e}")
            time.sleep(5)  # Wait before retrying

def process_batch_sync(batch_id: str, files_data: List[Dict], user_id: str = None):
    """Synchronously process a batch (runs in background thread)"""
    try:
        print(f"🚀 Starting batch processing for batch_id: {batch_id}")
        print(f"📁 Processing {len(files_data)} files for user: {user_id}")
        
        total_files = len(files_data)
        processed_files = 0
        failed_files = 0
        results = []
        
        # Update batch status to processing
        print(f"📊 Updating batch status to processing...")
        update_batch_progress(batch_id, processed_files, total_files, "processing")
        print(f"✅ Batch status updated successfully")
        
        for i, file_info in enumerate(files_data):
            try:
                print(f"🔄 Processing file {i+1}/{total_files}: {file_info.get('filename', 'unknown')}")
                
                # Process individual file
                result = process_single_file(file_info, batch_id, user_id)
                results.append(result)
                
                if result['success']:
                    processed_files += 1
                    print(f"✅ File {i+1} processed successfully")
                else:
                    failed_files += 1
                    print(f"❌ File {i+1} failed: {result.get('error', 'Unknown error')}")
                    
                # Update batch progress in database
                update_batch_progress(batch_id, processed_files, total_files, "processing")
                
            except Exception as file_error:
                print(f"💥 Critical error processing file {i+1} ({file_info.get('filename', 'unknown')}): {file_error}")
                import traceback
                traceback.print_exc()
                failed_files += 1
                results.append({
                    'filename': file_info.get('filename', 'unknown'),
                    'success': False,
                    'error': str(file_error)
                })
        
        # Final status update
        final_status = "completed" if failed_files == 0 else "completed_with_errors"
        update_batch_progress(batch_id, processed_files, total_files, final_status)
        
        print(f"🎉 Batch processing completed!")
        print(f"📊 Results: {processed_files}/{total_files} files processed successfully")
        print(f"❌ Failed files: {failed_files}")
        
        return {
            'batch_id': batch_id,
            'status': final_status,
            'total_files': total_files,
            'processed_files': processed_files,
            'failed_files': failed_files,
            'results': results
        }
        
    except Exception as e:
        print(f"💥 Critical batch processing error: {e}")
        import traceback
        traceback.print_exc()
        update_batch_progress(batch_id, processed_files, total_files, "failed")

def queue_batch_for_processing(batch_id: str, files_data: List[Dict], user_id: str = None):
    """Queue a batch for background processing"""
    batch_data = {
        'batch_id': batch_id,
        'files_data': files_data,
        'user_id': user_id
    }
    
    batch_queue.put(batch_data)
    print(f"📋 Batch {batch_id} queued for processing")
    
    # Start processor if not running
    start_background_processor()

def stop_background_processor():
    """Stop the background processor"""
    global is_processing
    is_processing = False
    print("🛑 Background processor stopped")
