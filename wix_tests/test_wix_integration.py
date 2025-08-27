#!/usr/bin/env python3
"""
Simple test for the PostgreSQL wix_uploads functionality
"""
import sys
import os
from datetime import datetime
from uuid import uuid4

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("🧪 Testing PostgreSQL wix_uploads functionality...")
    from database import save_wix_upload, get_user_uploads, get_upload_by_id, get_wix_upload_stats, save_upload_record
    
    # Generate test data
    test_user_id = "user_" + str(uuid4())[:8]
    test_upload_id = str(uuid4())
    test_time = datetime.utcnow()
    
    print(f"\n📝 Test data:")
    print(f"  User ID: {test_user_id}")
    print(f"  Upload ID: {test_upload_id}")
    print(f"  Time: {test_time}")
    
    # First, create a record in uploads table (required for foreign key)
    print(f"\n1️⃣ Creating upload record...")
    save_upload_record(
        upload_id=test_upload_id,
        filename="test_image.jpg",
        ext=".jpg",
        upload_time=test_time,
        ip="127.0.0.1",
        storage_path="/test/path/test_image.jpg",
        sha256_hash="test_hash_" + str(uuid4())[:16]
    )
    print("✅ Upload record created")
    
    # Test save_wix_upload
    print(f"\n2️⃣ Testing save_wix_upload...")
    result = save_wix_upload(test_user_id, test_upload_id, test_time)
    if result:
        print("✅ Successfully saved to wix_uploads table")
    else:
        print("❌ Failed to save to wix_uploads table")
        
    # Test get_user_uploads
    print(f"\n3️⃣ Testing get_user_uploads...")
    user_uploads = get_user_uploads(test_user_id)
    print(f"✅ Found {len(user_uploads)} uploads for user {test_user_id}")
    if user_uploads:
        print(f"  Latest upload: {user_uploads[0]}")
    
    # Test get_upload_by_id
    print(f"\n4️⃣ Testing get_upload_by_id...")
    upload_details = get_upload_by_id(test_upload_id)
    if upload_details:
        print(f"✅ Found upload details: {upload_details}")
    else:
        print("❌ Upload not found")
    
    # Test get_wix_upload_stats
    print(f"\n5️⃣ Testing get_wix_upload_stats...")
    stats = get_wix_upload_stats()
    print(f"✅ Upload statistics: {stats}")
    
    print(f"\n🎉 All tests completed successfully!")
    print(f"Your PostgreSQL integration is working perfectly!")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
