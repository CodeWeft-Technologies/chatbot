"""
Background worker for processing file ingestion jobs from queue.

Polls ingest_jobs table for pending jobs and processes them asynchronously.
"""

import asyncio
import logging
import psycopg
from uuid import UUID
import gc
import torch
import ctypes
import sys
import psutil
import subprocess
import os
from app.config import settings

logger = logging.getLogger(__name__)


async def start_background_worker():
    """Start the background worker that processes ingestion jobs."""
    print("[WORKER] 🚀 Starting background ingestion worker...")
    logger.info("[WORKER] 🚀 Starting background ingestion worker...")
    
    # Give the main app a moment to initialize
    await asyncio.sleep(2)
    
    # Create a task to process jobs concurrently
    process_task = asyncio.create_task(process_jobs_concurrently())
    
    try:
        await process_task
    except Exception as e:
        print(f"[WORKER] ❌ Worker crashed: {e}")
        logger.error(f"[WORKER] ❌ Worker crashed: {e}", exc_info=True)


async def process_jobs_concurrently():
    """Process multiple jobs concurrently with a max limit."""
    MAX_CONCURRENT_JOBS = 1  # Only 1 job at a time for memory safety
    active_tasks = set()
    
    while True:  # Keep running forever - idle cost is minimal
        try:
            # Check for pending jobs and start new tasks if slots available
            while len(active_tasks) < MAX_CONCURRENT_JOBS:
                job = _get_next_pending_job()
                if not job:
                    break  # No more pending jobs
                
                job_id = job[0]
                # Create task for this job
                task = asyncio.create_task(_process_job_wrapper(job))
                active_tasks.add(task)
                
                # Clean up completed tasks
                done = [t for t in active_tasks if t.done()]
                for t in done:
                    active_tasks.discard(t)
                    try:
                        await t  # Get any exceptions
                    except Exception as e:
                        logger.error(f"[WORKER] Task error: {e}")
            
            # Wait a bit before checking for new jobs
            await asyncio.sleep(2)
            
            # Clean up completed tasks
            done = [t for t in active_tasks if t.done()]
            for t in done:
                active_tasks.discard(t)
                try:
                    await t
                except Exception as e:
                    logger.error(f"[WORKER] Task error: {e}")
        
        except Exception as e:
            print(f"[WORKER] ❌ Error in concurrent processor: {e}")
            logger.error(f"[WORKER] ❌ Error in concurrent processor: {e}")
            await asyncio.sleep(2)


def _get_next_pending_job():
    """Get the next pending job without starting async processing."""
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                # Get next pending job
                cur.execute("""
                    SELECT id, org_id, bot_id, filename, file_size
                    FROM ingest_jobs
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """)
                
                job = cur.fetchone()
                if not job:
                    return None
                
                job_id, org_id, bot_id, filename, file_size = job
                
                # Mark as processing
                cur.execute("""
                    UPDATE ingest_jobs
                    SET status = 'processing', started_at = NOW(), progress = 0
                    WHERE id = %s
                """, (job_id,))
                conn.commit()
                
                logger.info(f"[WORKER] ⏳ Found pending job: {job_id}")
                print(f"[WORKER] ⏳ Found pending job: {job_id}")
                
                return job
    except Exception as e:
        logger.error(f"[WORKER] Error getting job: {e}")
        return None


async def _process_job_wrapper(job):
    """Wrapper to process a job from tuple."""
    job_id, org_id, bot_id, filename, file_size = job
    await _process_job(job_id, org_id, bot_id, filename, file_size)


async def _process_job(job_id: str, org_id: str, bot_id: str, filename: str, 
                       file_size: int):
    """Process a single ingestion job - actual file processing."""
    try:
        msg = f"[WORKER-{job_id}] 🚀 Starting file processing: {filename}"
        logger.info(msg)
        print(msg)
        
        # Update progress: extracting
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_jobs SET progress = 20 WHERE id = %s", (job_id,))
                conn.commit()
        
        msg = f"[WORKER-{job_id}] 📊 Progress: 20% (Extracting elements...)"
        logger.info(msg)
        print(msg)
        
        # Run processing in isolated subprocess for guaranteed memory cleanup
        msg = f"[WORKER-{job_id}] 🚀 Starting subprocess for complete memory isolation..."
        logger.info(msg)
        print(msg)
        
        # Get Python executable from current environment
        python_exe = sys.executable
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'process_single_job.py')
        
        # Run subprocess and capture output
        proc = await asyncio.create_subprocess_exec(
            python_exe, script_path, job_id, org_id, bot_id, filename,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy()
        )
        
        stdout, stderr = await proc.communicate()
        
        # Parse result from subprocess
        output = stdout.decode()
        error_output = stderr.decode()
        
        if error_output:
            print(f"[WORKER-{job_id}] Subprocess stderr: {error_output}")
        
        # Look for RESULT line in output
        inserted = 0
        skipped = 0
        for line in output.split('\n'):
            if line.startswith('RESULT|'):
                parts = line.split('|')
                inserted = int(parts[1])
                skipped = int(parts[2])
                break
            elif line.startswith('ERROR|'):
                error_msg = line.split('|', 1)[1]
                raise Exception(f"Subprocess error: {error_msg}")
        
        if proc.returncode != 0:
            raise Exception(f"Subprocess failed with code {proc.returncode}: {output}")
        
        msg = f"[WORKER-{job_id}] ✓ Subprocess completed: {inserted} inserted, {skipped} skipped"
        logger.info(msg)
        print(msg)
        
        # Add delay so frontend can poll 40%
        await asyncio.sleep(2)
        
        # Update progress: 40% (halfway through extraction)
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_jobs SET progress = 40 WHERE id = %s", (job_id,))
                conn.commit()
        
        msg = f"[WORKER-{job_id}] 📊 Progress: 40% (Processing chunks...)"
        logger.info(msg)
        print(msg)
        
        # Add delay so frontend can poll 60%
        await asyncio.sleep(2)
        
        # Update progress: 60% (three-quarters through)
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_jobs SET progress = 60 WHERE id = %s", (job_id,))
                conn.commit()
        
        msg = f"[WORKER-{job_id}] 📊 Progress: 60% (Creating embeddings...)"
        logger.info(msg)
        print(msg)
        
        # Add delay so frontend can poll 90%
        await asyncio.sleep(2)
        
        msg = f"[WORKER-{job_id}] ⏳ Finalizing..."
        logger.info(msg)
        print(msg)
        
        # Update progress: 90% (almost done)
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_jobs SET progress = 90 WHERE id = %s", (job_id,))
                conn.commit()
        
        msg = f"[WORKER-{job_id}] 📊 Progress: 90% (Finalizing...)"
        logger.info(msg)
        print(msg)
        
        # Add delay so frontend can poll 100%
        await asyncio.sleep(1)
        
        # Mark as completed
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE ingest_jobs
                    SET status = 'completed', 
                        progress = 100, 
                        completed_at = NOW(),
                        documents_count = %s
                    WHERE id = %s
                """, (inserted, job_id))
                conn.commit()
        
        msg = f"[WORKER-{job_id}] ✅ COMPLETED: {inserted} documents ingested successfully!"
        logger.info(msg)
        print(msg)
    
    except Exception as e:
        msg = f"[WORKER-{job_id}] ❌ Processing failed: {e}"
        logger.error(msg, exc_info=True)
        print(msg)
        import traceback
        traceback.print_exc()
        
        # Mark as failed
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE ingest_jobs
                    SET status = 'failed', 
                        completed_at = NOW(),
                        error_message = %s
                    WHERE id = %s
                """, (str(e)[:500], job_id))
                conn.commit()


async def get_job_status(job_id: UUID | str) -> dict:
    """Get the current status of an ingestion job."""
    try:
        # Convert to string if UUID
        job_id_str = str(job_id)
        
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, filename, status, progress, created_at, 
                           started_at, completed_at, error_message, documents_count
                    FROM ingest_jobs
                    WHERE id = %s
                """, (job_id_str,))
                
                row = cur.fetchone()
                if not row:
                    return None
                
                (jid, fname, status, progress, created, started, completed, 
                 error, doc_count) = row
                
                return {
                    "id": str(jid),
                    "filename": fname,
                    "status": status,
                    "progress": progress,
                    "created_at": created.isoformat() if created else None,
                    "started_at": started.isoformat() if started else None,
                    "completed_at": completed.isoformat() if completed else None,
                    "error": error,
                    "documents_count": doc_count
                }
    
    except Exception as e:
        logger.error(f"[WORKER] Error getting job status: {e}")
        return None


async def get_user_jobs(org_id: UUID, limit: int = 20) -> list:
    """Get recent ingestion jobs for an organization."""
    try:
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, filename, status, progress, created_at, 
                           started_at, completed_at, documents_count
                    FROM ingest_jobs
                    WHERE org_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (org_id, limit))
                
                rows = cur.fetchall()
                return [
                    {
                        "id": str(row[0]),
                        "filename": row[1],
                        "status": row[2],
                        "progress": row[3],
                        "created_at": row[4].isoformat() if row[4] else None,
                        "started_at": row[5].isoformat() if row[5] else None,
                        "completed_at": row[6].isoformat() if row[6] else None,
                        "documents_count": row[7]
                    }
                    for row in rows
                ]
    
    except Exception as e:
        logger.error(f"[WORKER] Error getting user jobs: {e}")
        return []
