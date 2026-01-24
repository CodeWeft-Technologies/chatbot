#!/usr/bin/env python3
"""
Inspect chunks stored in the database for a specific file.
"""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    exit(1)

try:
    conn = psycopg.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Query the latest chunks (assuming you want the most recent file)
    cursor.execute("""
        SELECT 
            id,
            content,
            metadata::jsonb->'source_file' as source_file,
            metadata::jsonb->'extraction_method' as extraction_method,
            metadata::jsonb->'page' as page,
            created_at
        FROM rag_embeddings
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    
    if not rows:
        print("❌ No chunks found in database")
        exit(1)
    
    print(f"\n📄 Found {len(rows)} recent chunks:\n")
    print("=" * 100)
    
    for idx, (chunk_id, content, source_file, extraction_method, page, created_at) in enumerate(rows, 1):
        print(f"\n🔹 Chunk #{idx}")
        print(f"   ID: {chunk_id}")
        print(f"   Source File: {source_file}")
        print(f"   Extraction Method: {extraction_method}")
        print(f"   Page: {page}")
        print(f"   Created: {created_at}")
        print(f"   Content Preview (first 300 chars):")
        print(f"   {content[:300]}..." if len(content) > 300 else f"   {content}")
        print(f"   Full Length: {len(content)} characters")
        print("-" * 100)
    
    cursor.close()
    conn.close()
    print("\n✅ Done!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
