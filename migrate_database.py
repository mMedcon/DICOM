#!/usr/bin/env python3
"""
Database migration script to add batch_id column and create upload_batches table
Run this if you already have an existing database
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Updating database schema for batch uploads...")
    from database import conn, cur
    
    # Check if batch_id column exists in uploads table
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='uploads' AND column_name='batch_id';
    """)
    
    if not cur.fetchone():
        print("Adding batch_id column to uploads table...")
        cur.execute("ALTER TABLE public.uploads ADD COLUMN batch_id UUID;")
        print("✓ Added batch_id column")
    else:
        print("✓ batch_id column already exists")
    
    # Check if upload_batches table exists
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name='upload_batches';
    """)
    
    if not cur.fetchone():
        print("Creating upload_batches table...")
        cur.execute("""
            CREATE TABLE public.upload_batches (
                batch_id UUID PRIMARY KEY,
                user_id TEXT,
                total_files INT NOT NULL,
                processed_files INT DEFAULT 0,
                status TEXT DEFAULT 'queued',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("✓ Created upload_batches table")
    else:
        print("✓ upload_batches table already exists")
    
    print("✅ Database schema updated successfully!")
    
except Exception as e:
    print(f"❌ Database schema update failed: {e}")
    import traceback
    traceback.print_exc()
