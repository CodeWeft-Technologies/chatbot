"""
Enhanced RAG utilities with semantic chunking and content deduplication.
"""
from typing import List, Tuple, Optional, Set
from datetime import datetime
import psycopg
from psycopg.types.json import Json
import hashlib
import logging
from openai import OpenAI

from app.config import settings
from app.db import get_conn, vector_search, normalize_org_id, normalize_bot_id

logger = logging.getLogger(__name__)

try:
    import nltk
    NLTK_AVAILABLE = True
    
    # Download required NLTK data on first import
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        try:
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
        except Exception as e:
            logger.warning(f"NLTK data download failed: {e}")
except ImportError:
    NLTK_AVAILABLE = False
    logger.warning("NLTK not available - using fallback chunking")

# Initialize OpenAI client
_openai_client = None


def _get_openai_client():
    """Get or create OpenAI client for embeddings"""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def unload_model():
    """No-op for API-based embeddings (kept for backward compatibility)"""
    pass


def check_and_unload_if_idle():
    """No-op for API-based embeddings (kept for backward compatibility)"""
    return False


def embed_text(text: str) -> List[float]:
    """
    Generate embedding vector for text using OpenAI API.
    """
    try:
        client = _get_openai_client()
        response = client.embeddings.create(
            input=text,
            model=settings.EMBEDDING_MODEL_NAME
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"❌ [EMBEDDING] Error generating OpenAI embedding: {e}", flush=True)
        logger.error(f"❌ Error generating OpenAI embedding: {e}")
        raise


def chunk_text_semantic(
    text: str,
    min_chunk_size: int = 200,
    max_chunk_size: int = 1500,
    overlap_sentences: int = 1,
) -> List[str]:
    """
    Chunk text using semantic boundaries (sentences).
    
    Args:
        text: Text to chunk
        min_chunk_size: Minimum characters per chunk (soft limit)
        max_chunk_size: Maximum characters per chunk (hard limit)
        overlap_sentences: Number of sentences to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not NLTK_AVAILABLE:
        logger.warning("NLTK not available, using fallback chunking")
        return chunk_text_fallback(text, max_chunk_size, 200)
    
    try:
        # Split into sentences
        sentences = nltk.sent_tokenize(text)
    except Exception as e:
        logger.warning(f"NLTK sentence tokenization failed: {e}")
        return chunk_text_fallback(text, max_chunk_size, 200)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for i, sentence in enumerate(sentences):
        sentence_length = len(sentence)
        
        # If single sentence exceeds max, split it
        if sentence_length > max_chunk_size:
            # Flush current chunk if any
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
            
            # Split long sentence by character limit
            for j in range(0, len(sentence), max_chunk_size - 100):
                chunk_part = sentence[j:j + max_chunk_size]
                chunks.append(chunk_part)
            continue
        
        # Check if adding this sentence would exceed max
        if current_length + sentence_length > max_chunk_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            
            # Add overlap
            if overlap_sentences > 0 and len(current_chunk) > overlap_sentences:
                current_chunk = current_chunk[-overlap_sentences:]
                current_length = sum(len(s) for s in current_chunk) + len(current_chunk) - 1
            else:
                current_chunk = []
                current_length = 0
        
        current_chunk.append(sentence)
        current_length += sentence_length + 1  # +1 for space
    
    # Add final chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        # Only add if meets minimum size or is the only chunk
        if len(chunk_text.strip()) >= min_chunk_size or not chunks:
            chunks.append(chunk_text)
        elif chunks and chunk_text.strip():
            # Append to last chunk if too small (only if it's not empty)
            chunks[-1] += " " + chunk_text
    
    return [c.strip() for c in chunks if c.strip()]


def chunk_text_fallback(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Fallback chunking with fixed size and overlap.
    Used when NLTK is unavailable.
    """
    chunks: List[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += chunk_size - overlap
    return [c for c in chunks if c.strip()]


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Chunk text - uses semantic chunking if available, otherwise falls back to fixed-size.
    
    This function maintains backward compatibility with the original interface
    while preferring semantic chunking when NLTK is available.
    """
    if NLTK_AVAILABLE:
        try:
            return chunk_text_semantic(text, min_chunk_size=100, max_chunk_size=chunk_size)
        except Exception as e:
            logger.warning(f"Semantic chunking failed: {e}")
    
    return chunk_text_fallback(text, chunk_size, overlap)


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of normalized content for deduplication"""
    # Normalize: strip whitespace, lowercase
    normalized = " ".join(content.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def is_duplicate_content(
    org_id: str,
    bot_id: str,
    content: str,
    similarity_threshold: float = 0.95,
) -> bool:
    """
    Check if content is duplicate using hash-based deduplication.
    
    Args:
        org_id: Organization ID
        bot_id: Bot ID
        content: Content to check
        similarity_threshold: Not used in hash-based approach (kept for interface compatibility)
    
    Returns:
        True if duplicate exists
    """
    content_hash = compute_content_hash(content)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check if we already have this content hash
            cur.execute(
                """
                SELECT 1 FROM rag_embeddings 
                WHERE org_id = %s 
                  AND bot_id = %s 
                  AND metadata->>'content_hash' = %s
                LIMIT 1
                """,
                (normalize_org_id(org_id), normalize_bot_id(bot_id), content_hash),
            )
            return cur.fetchone() is not None


def store_embedding(
    org_id: str,
    bot_id: str,
    content: str,
    embedding: List[float],
    metadata: Optional[dict] = None,
    skip_duplicate_check: bool = False,
) -> bool:
    """
    Store embedding with automatic deduplication.
    
    Args:
        org_id: Organization ID
        bot_id: Bot ID
        content: Content text
        embedding: Embedding vector
        metadata: Optional metadata dict
        skip_duplicate_check: Skip deduplication check (for bulk operations)
    
    Returns:
        True if stored, False if duplicate
    """
    # Check for duplicates
    if not skip_duplicate_check and is_duplicate_content(org_id, bot_id, content):
        logger.debug(f"Skipping duplicate content (hash match)")
        return False
    
    # Add content hash to metadata
    if metadata is None:
        metadata = {}
    metadata["content_hash"] = compute_content_hash(content)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            oid = normalize_org_id(org_id)
            bid = normalize_bot_id(bot_id)
            
            # Ensure organization exists
            try:
                cur.execute("SELECT 1 FROM organizations WHERE id=%s", (oid,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO organizations (id, name) VALUES (%s, %s)",
                        (oid, org_id)
                    )
            except Exception as e:
                logger.warning(f"Organization check failed: {e}")
            
            # Insert embedding
            cur.execute(
                """
                INSERT INTO rag_embeddings 
                (org_id, bot_id, content, embedding, metadata, created_at) 
                VALUES (%s, %s, %s, %s::vector, %s, %s)
                """,
                (
                    oid,
                    bid,
                    content,
                    embedding,
                    Json(metadata),
                    datetime.utcnow(),
                ),
            )
    
    return True


def search_top_chunks(
    org_id: str,
    bot_id: str,
    query: str,
    top_k: int
) -> List[Tuple[str, dict, float]]:
    """
    Search for top-k most similar chunks to query.
    
    Returns:
        List of (content, metadata, similarity_score) tuples
    """
    qvec = embed_text(query)
    rows = vector_search(org_id, bot_id, qvec, k=top_k)
    return rows


def remove_boilerplate(text: str) -> str:
    """
    Remove common boilerplate patterns from text.
    
    Removes:
    - Cookie notices
    - Newsletter signups
    - Social media prompts
    - Navigation text
    """
    boilerplate_patterns = [
        # Cookie notices
        r"(?i)this (website|site) uses cookies",
        r"(?i)by continuing to (use|browse)",
        r"(?i)we use cookies",
        r"(?i)accept (all )?cookies",
        
        # Newsletter/signup
        r"(?i)sign up for (our )?newsletter",
        r"(?i)subscribe to (our )?newsletter",
        r"(?i)join our mailing list",
        
        # Social media
        r"(?i)follow us on",
        r"(?i)share (this|on)",
        
        # Navigation
        r"(?i)skip to (main )?content",
        r"(?i)jump to navigation",
    ]
    
    import re
    cleaned = text
    for pattern in boilerplate_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)
    return cleaned.strip()
