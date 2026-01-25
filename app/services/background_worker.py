"""
Background worker for processing file ingestion jobs from queue.

Polls ingest_jobs table for pending jobs and processes them asynchronously.
"""

import asyncio
import logging
import psycopg
from uuid import UUID
from app.config import settings
from app.services.enhanced_rag import process_multimodal_file

logger = logging.getLogger(__name__)


async def start_background_worker():
    """Start the background worker that processes ingestion jobs."""
    logger.info("[WORKER] Starting background ingestion worker...")
    
    # Give the main app a moment to initialize
    await asyncio.sleep(2)
    
    while True:
        try:
            await process_pending_jobs()
        except Exception as e:
            logger.error(f"[WORKER] Error in main loop: {e}")
        
        # Poll every 2 seconds
        await asyncio.sleep(2)


async def process_pending_jobs():
    """Poll database for pending jobs and process them."""
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
                """)
                
                job = cur.fetchone()
                if not job:
                    # Silently return if no jobs
                    return  # No pending jobs
                
                job_id, org_id, bot_id, filename, file_size = job
                
                # Mark as processing
                cur.execute("""
                    UPDATE ingest_jobs
                    SET status = 'processing', started_at = NOW(), progress = 0
                    WHERE id = %s
                """, (job_id,))
                conn.commit()
                
                logger.info(f"[WORKER] ⏳ Found pending job: {job_id}")
                logger.info(f"[WORKER]    File: {filename} ({file_size} bytes)")
        
        # Process the job (outside transaction)
        await _process_job(job_id, org_id, bot_id, filename, file_size)
    
    except Exception as e:
        logger.error(f"[WORKER] Error processing pending jobs: {e}")


async def _process_job(job_id: str, org_id: str, bot_id: str, filename: str, 
                       file_size: int):
    """Process a single ingestion job - actual file processing."""
    try:
        logger.info(f"[WORKER-{job_id}] 🚀 Starting file processing: {filename}")
        
        # Fetch file bytes from database
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT file_content FROM ingest_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                if not row:
                    raise Exception(f"Job {job_id} not found in database")
                file_bytes = row[0]
        
        logger.info(f"[WORKER-{job_id}] ✓ Retrieved {len(file_bytes)} bytes from database")
        
        # Update progress: extracting
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_jobs SET progress = 20 WHERE id = %s", (job_id,))
                conn.commit()
        
        logger.info(f"[WORKER-{job_id}] 📊 Progress: 20% (Extracting elements...)")
        
        # Process multimodal file
        logger.info(f"[WORKER-{job_id}] 🧠 Calling process_multimodal_file...")
        inserted, skipped = await process_multimodal_file(
            filename=filename,
            file_bytes=file_bytes,
            org_id=org_id,
            bot_id=bot_id,
        )
        
        logger.info(f"[WORKER-{job_id}] ✓ Extraction complete: {inserted} inserted, {skipped} skipped")
        
        # Update progress: embedding
        with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_jobs SET progress = 80 WHERE id = %s", (job_id,))
                conn.commit()
        
        logger.info(f"[WORKER-{job_id}] 📊 Progress: 80% (Creating embeddings...)")
        logger.info(f"[WORKER-{job_id}] ⏳ Finalizing...")
        
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
        
        logger.info(f"[WORKER-{job_id}] ✅ COMPLETED: {inserted} documents ingested successfully!")
        
        # Unload model to free memory
        try:
            from app.services.enhanced_rag import unload_model
            unload_model()
        except Exception as e:
            logger.warning(f"[WORKER-{job_id}] Failed to unload model: {e}")
    
    except Exception as e:
        logger.error(f"[WORKER-{job_id}] ❌ Processing failed: {e}", exc_info=True)
        
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
