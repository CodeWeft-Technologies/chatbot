-- Alternative Schema for Railway (Without pgvector)
-- Uses JSONB to store embeddings as JSON arrays

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Modified rag_embeddings table (without vector type)
CREATE TABLE IF NOT EXISTS rag_embeddings (
  id BIGSERIAL PRIMARY KEY,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  doc_id TEXT,
  chunk_id INT,
  content TEXT NOT NULL,
  -- Store embedding as JSONB array instead of vector
  embedding JSONB NOT NULL,  
  embedding_dim INT DEFAULT 1024,  -- Track dimensionality
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for rag_embeddings
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_org_bot ON rag_embeddings(org_id, bot_id);
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_bot ON rag_embeddings(bot_id);
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_doc ON rag_embeddings(doc_id);

-- GIN index for JSONB embedding (helps with some queries)
CREATE INDEX IF NOT EXISTS idx_rag_embeddings_embedding_gin ON rag_embeddings USING GIN (embedding);

-- Note: Without pgvector, you'll need to implement cosine similarity in application code
-- Example Python code for cosine similarity:

/*
import numpy as np
from typing import List

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    return dot_product / (norm1 * norm2)

def vector_search(query_embedding: List[float], limit: int = 6):
    # Fetch all embeddings (or filter by org/bot first)
    cursor.execute(
        "SELECT id, content, embedding, metadata FROM rag_embeddings WHERE org_id = %s AND bot_id = %s",
        (org_id, bot_id)
    )
    
    results = []
    for row in cursor.fetchall():
        emb_id, content, embedding_json, metadata = row
        embedding = json.loads(embedding_json) if isinstance(embedding_json, str) else embedding_json
        similarity = cosine_similarity(query_embedding, embedding)
        results.append((similarity, content, metadata))
    
    # Sort by similarity and return top k
    results.sort(reverse=True, key=lambda x: x[0])
    return results[:limit]
*/

-- Sample insert (embeddings stored as JSON arrays)
-- INSERT INTO rag_embeddings (org_id, bot_id, content, embedding)
-- VALUES ('org1', 'bot1', 'Sample text', '[0.1, 0.2, 0.3, ...]'::jsonb);

-- All other tables remain the same (copy from railway_complete_schema.sql)
