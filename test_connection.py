#!/usr/bin/env python3
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing database connection...")
    from database import conn, cur
    
    # Test connection
    cur.execute("SELECT 1")
    result = cur.fetchone()
    print(f"✅ Database connection successful: {result}")
    
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()

try:
    print("\nTesting dicom_utils functions...")
    from dicom_utils import convert_to_dicom, anonymize_dicom, encrypt_file
    print("✅ dicom_utils imports successful")
    
except Exception as e:
    print(f"❌ dicom_utils import failed: {e}")
    import traceback
    traceback.print_exc()
