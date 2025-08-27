#!/usr/bin/env python3
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Creating database tables...")
    from database import conn, cur
    
    # Read SQL file
    with open('init.sql', 'r') as f:
        sql_content = f.read()
    
    # Split by semicolon and execute each statement
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
    
    for i, statement in enumerate(statements):
        print(f"Executing statement {i+1}: {statement[:50]}...")
        cur.execute(statement)
    
    print(" All database tables created successfully!")
    
except Exception as e:
    print(f"Database table creation failed: {e}")
    import traceback
    traceback.print_exc()
