#!/usr/bin/env python
"""
Subprocess script to process a single ingestion job with complete memory isolation.
When this process exits, ALL memory (including Unstructured models) is freed by the OS.
"""
import sys
import asyncio
import psycopg
from app.config import settings
from app.services.enhanced_rag import process_multimodal_file


async def main():
    """Process a single job and exit - memory will be freed automatically."""
    if len(sys.argv) != 5:
        print("Usage: process_single_job.py <job_id> <org_id> <bot_id> <filename>")
        sys.exit(1)
    
    job_id = sys.argv[1]
    org_id = sys.argv[2]
    bot_id = sys.argv[3]
    filename = sys.argv[4]
    
    try:
        print(f"[SUBPROCESS-{job_id}] Starting processing: {filename}")
        
        # Fetch file bytes from database
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT file_content FROM ingest_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                if not row:
                    raise Exception(f"Job {job_id} not found")
                file_bytes = row[0]
        
        print(f"[SUBPROCESS-{job_id}] Retrieved {len(file_bytes)} bytes")
        
        # Process the file
        inserted, skipped = await process_multimodal_file(
            filename=filename,
            file_bytes=file_bytes,
            org_id=org_id,
            bot_id=bot_id,
        )
        
        print(f"[SUBPROCESS-{job_id}] SUCCESS: {inserted} inserted, {skipped} skipped")
        
        # Return result via stdout in format: SUCCESS|inserted|skipped
        print(f"RESULT|{inserted}|{skipped}")
        sys.exit(0)
        
    except Exception as e:
        print(f"[SUBPROCESS-{job_id}] ERROR: {e}")
        print(f"ERROR|{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
