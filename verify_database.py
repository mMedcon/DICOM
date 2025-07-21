#!/usr/bin/env python3
"""
Script to verify database tables were created successfully
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Verifying database tables...")
    from database import conn, cur
    
    # List all tables
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    
    tables = cur.fetchall()
    print(f"\n✅ Found {len(tables)} tables in the database:")
    for table in tables:
        print(f"  - {table[0]}")
    
    # Check wix_uploads table structure
    print("\n📊 wix_uploads table structure:")
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = 'wix_uploads' 
        ORDER BY ordinal_position;
    """)
    
    columns = cur.fetchall()
    for col in columns:
        nullable = "NULL" if col[2] == "YES" else "NOT NULL"
        default = f" DEFAULT {col[3]}" if col[3] else ""
        print(f"  - {col[0]}: {col[1]} {nullable}{default}")
    
    # Test inserting a sample record (will rollback)
    print("\n🧪 Testing insert functionality...")
    from datetime import datetime
    test_user_id = "test_user_123"
    test_upload_id = "123e4567-e89b-12d3-a456-426614174000"  # Sample UUID
    test_time = datetime.utcnow()
    
    # First, we need to insert into uploads table since wix_uploads references it
    cur.execute("""
        INSERT INTO public.uploads (id, original_filename, file_type, upload_time, uploader_ip, storage_path, sha256_hash, encrypted, status)
        VALUES (%s, 'test.jpg', '.jpg', %s, '127.0.0.1', '/test/path', 'test_hash', TRUE, 'test')
    """, (test_upload_id, test_time))
    
    # Now test wix_uploads insert
    cur.execute("""
        INSERT INTO public.wix_uploads (user_id, upload_id, upload_time)
        VALUES (%s, %s, %s)
    """, (test_user_id, test_upload_id, test_time))
    
    # Verify the insert worked
    cur.execute("""
        SELECT wu.user_id, wu.upload_id, wu.upload_time, u.original_filename
        FROM public.wix_uploads wu
        JOIN public.uploads u ON wu.upload_id = u.id
        WHERE wu.user_id = %s
    """, (test_user_id,))
    
    result = cur.fetchone()
    if result:
        print(f"  ✅ Test insert successful: {result}")
    
    # Rollback the test data
    conn.rollback()
    print("  🔄 Test data rolled back")
    
    print("\n🎉 Database setup verification complete!")
    print("Your PostgreSQL database is ready for the DICOM service with user tracking!")
    
except Exception as e:
    print(f"❌ Database verification failed: {e}")
    import traceback
    traceback.print_exc()
