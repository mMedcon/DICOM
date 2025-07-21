#!/usr/bin/env python3
"""
Test script to simulate a file upload with user ID (like from Wix frontend)
"""
import requests
import os
from datetime import datetime

def test_upload_with_user_id():
    """Test the upload endpoint with user ID header"""
    
    # Test data
    test_user_id = "test_user_12345"
    test_filename = "test_image.jpg"
    
    # Create a small test file
    test_file_content = b"This is a test image file content for DICOM upload testing"
    
    print("🧪 Testing DICOM Upload with User ID")
    print(f"User ID: {test_user_id}")
    print(f"Filename: {test_filename}")
    print(f"File size: {len(test_file_content)} bytes")
    
    try:
        # Make the upload request
        response = requests.post(
            "http://localhost:8000/upload",
            headers={
                "X-File-Name": test_filename,
                "X-User-ID": test_user_id,
                "Content-Type": "image/jpeg"
            },
            data=test_file_content,
            timeout=30
        )
        
        print(f"\n📤 Upload Response:")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Upload successful!")
            print(f"Upload ID: {result.get('upload_id')}")
            print(f"Message: {result.get('message')}")
            print(f"Diagnosis: {result.get('diagnosis')}")
            print(f"Confidence: {result.get('confidence')}")
            
            upload_id = result.get('upload_id')
            
            # Test getting user uploads
            print(f"\n📋 Testing get user uploads...")
            user_uploads_response = requests.get(f"http://localhost:8000/user/{test_user_id}/uploads")
            if user_uploads_response.status_code == 200:
                user_data = user_uploads_response.json()
                print(f"✅ Found {user_data['count']} uploads for user {test_user_id}")
                if user_data['uploads']:
                    print(f"Latest upload: {user_data['uploads'][0]}")
            
            # Test getting upload details
            print(f"\n🔍 Testing get upload details...")
            details_response = requests.get(f"http://localhost:8000/upload/{upload_id}/details")
            if details_response.status_code == 200:
                details = details_response.json()
                print(f"✅ Upload details retrieved: {details}")
            
            # Test statistics
            print(f"\n📊 Testing upload statistics...")
            stats_response = requests.get("http://localhost:8000/stats")
            if stats_response.status_code == 200:
                stats = stats_response.json()
                print(f"✅ Upload statistics: {stats}")
                
        else:
            print(f"❌ Upload failed!")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed! Make sure the server is running on localhost:8000")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_server_status():
    """Test if the server is running"""
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running!")
            print(f"Response: {response.json()}")
            return True
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Server is not running or not accessible on localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Server test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 DICOM Service Integration Test")
    print("=" * 50)
    
    # Test server status first
    if test_server_status():
        print("\n" + "=" * 50)
        test_upload_with_user_id()
    else:
        print("\n💡 To start the server, run:")
        print("python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000")
