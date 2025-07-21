#!/usr/bin/env python3
"""
Script to add the wix_uploads table to an existing database
Run this if you already have a database set up and just want to add the new table
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Adding wix_uploads table to existing database...")
    from database import conn, cur
    
    # Create the wix_uploads table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS public.wix_uploads (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        user_id TEXT NOT NULL,
        upload_id UUID NOT NULL REFERENCES public.uploads(id),
        upload_time TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, upload_id)
    );
    """
    
    # Create indexes
    indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_wix_uploads_user_id ON public.wix_uploads(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_wix_uploads_upload_id ON public.wix_uploads(upload_id);",
        "CREATE INDEX IF NOT EXISTS idx_wix_uploads_time ON public.wix_uploads(upload_time);"
    ]
    
    print("Creating wix_uploads table...")
    cur.execute(create_table_sql)
    
    print("Creating indexes...")
    for index_sql in indexes_sql:
        cur.execute(index_sql)
    
    print("✅ wix_uploads table and indexes created successfully!")
    print("\nTable structure:")
    cur.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'wix_uploads' 
        ORDER BY ordinal_position;
    """)
    
    columns = cur.fetchall()
    for col in columns:
        print(f"  - {col[0]}: {col[1]} ({'NULL' if col[2] == 'YES' else 'NOT NULL'})")
    
except Exception as e:
    print(f"❌ Failed to add wix_uploads table: {e}")
    import traceback
    traceback.print_exc()
