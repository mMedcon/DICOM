#!/usr/bin/env python3
"""
Setup script for DICOM Batch Upload System
This script helps set up the required services and dependencies
"""

import subprocess
import sys
import os

def run_command(command, description):
    """Run a command and print the result"""
    print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} - Success")
            if result.stdout:
                print(result.stdout)
        else:
            print(f"❌ {description} - Failed")
            if result.stderr:
                print(result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ {description} - Error: {e}")
        return False

def main():
    print("🚀 DICOM Batch Upload System Setup")
    print("=" * 50)
    
    # Check if we're in a virtual environment
    if sys.prefix == sys.base_prefix:
        print("⚠️  Warning: You should run this from a virtual environment")
        print("   Run: python -m venv .venv && .venv\\Scripts\\activate")
    
    # Install Python dependencies
    run_command("pip install -r requirements.txt", "Installing Python dependencies")
    
    # Check if Docker is available for Redis
    if run_command("docker --version", "Checking Docker availability"):
        print("\n📦 You can run Redis using Docker:")
        print("   docker run -d -p 6379:6379 --name redis redis:alpine")
    else:
        print("\n📦 Docker not available. You'll need to install Redis manually:")
        print("   Windows: Download from https://github.com/microsoftarchive/redis/releases")
        print("   Linux/Mac: sudo apt install redis-server (or brew install redis)")
    
    # Update database schema
    run_command("python migrate_database.py", "Updating database schema")
    
    print("\n" + "=" * 50)
    print("🎯 Setup Complete! Next steps:")
    print("\n1. Start Redis server:")
    print("   - Docker: docker run -d -p 6379:6379 --name redis redis:alpine")
    print("   - Or install and run Redis locally")
    print("\n2. Start Celery worker (in a separate terminal):")
    print("   python -m celery --app=job_queue.celery_app worker --loglevel=info")
    print("\n3. Start the FastAPI server:")
    print("   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000")
    print("\n4. Test the endpoints:")
    print("   - Single upload: POST http://localhost:8000/upload")
    print("   - Batch upload: POST http://localhost:8000/upload/batch")
    print("   - Health check: GET http://localhost:8000/health")

if __name__ == "__main__":
    main()
