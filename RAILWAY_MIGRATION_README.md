# Railway Database Migration Guide

## ⚠️ IMPORTANT: Vector Extension Not Available

Railway's standard PostgreSQL does **NOT** include the `pgvector` extension by default. You have two options:

### Option 1: Install pgvector on Railway (Recommended)

You need to contact Railway support or use a Railway template that includes pgvector. Alternatively:

1. **Use Railway's pgvector template**: Deploy a new PostgreSQL instance using Railway's pgvector template
2. **Manual Installation**: SSH into your Railway PostgreSQL container and install pgvector (requires elevated permissions)

### Option 2: Use a Different Vector Database (Alternative)

If you cannot install pgvector on Railway, consider:

1. **Separate Vector Database**: Use Pinecone, Weaviate, or Qdrant for vector embeddings
2. **Keep Supabase for Vectors**: Use Railway for regular data, keep Supabase only for vector embeddings

## Current Status

✅ **Completed:**
- Schema dumped from Supabase (22 tables)
- Schema file created: `railway_complete_schema.sql`
- Connection to Railway PostgreSQL verified

❌ **Blocked:**
- Cannot create `vector` extension on Railway
- Rag_embeddings table requires `vector` data type

## Available Options on Railway PostgreSQL

Railway PostgreSQL 17.7 includes these extensions:
- ✅ uuid-ossp (for UUID generation)
- ✅ pg_trgm (text similarity/search)
- ✅ pgcrypto (encryption)
- ✅ hstore (key-value pairs)
- ❌ **vector/pgvector** (NOT AVAILABLE)

## Workaround: Modified Schema Without Vector

If you want to proceed without vector support, you can:

1. Store embeddings as JSON arrays instead of vector type
2. Modify the `rag_embeddings` table to use `REAL[]` or `JSONB`
3. Implement vector similarity search in application layer

### Modified Schema (Without Vector Extension)

```sql
-- Modified rag_embeddings without vector extension
CREATE TABLE rag_embeddings (
  id BIGSERIAL PRIMARY KEY,
  org_id TEXT NOT NULL,
  bot_id TEXT NOT NULL,
  doc_id TEXT,
  chunk_id INT,
  content TEXT NOT NULL,
  embedding JSONB NOT NULL,  -- Store as JSON array instead of vector
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create GIN index for JSON
CREATE INDEX idx_rag_embeddings_embedding ON rag_embeddings USING GIN (embedding);
```

## Recommended Solution

### Use Supabase for Vector Embeddings + Railway for Regular Data

Keep your current setup where:
- **Supabase**: Handles `rag_embeddings` table (has pgvector)
- **Railway**: Handles all other tables (bookings, users, chatbots, etc.)

### Implementation:

1. Create two database connections in your app:
   - `SUPABASE_DB_DSN`: For rag_embeddings table
   - `RAILWAY_DB_DSN`: For all other tables

2. Modify `app/db.py` to route queries appropriately

## Next Steps

Choose one of these paths:

### Path A: Install pgvector on Railway
1. Contact Railway support about pgvector
2. Or use Railway's pgvector template
3. Run migration script again

### Path B: Dual Database Setup  
1. Keep Supabase for vector embeddings
2. Use Railway for regular tables
3. Modify application to use both connections

### Path C: Alternative Vector Storage
1. Use Pinecone/Weaviate/Qdrant for vectors
2. Migrate all other tables to Railway
3. Update vector search code

## Migration Script Usage

Once pgvector is available on Railway:

```bash
cd backend
python dump_and_migrate_schema.py
```

This will:
1. Dump complete schema from Supabase
2. Apply to Railway PostgreSQL
3. Update .env file
4. Verify all tables created

## Files Created

- `railway_complete_schema.sql` - Complete schema dump
- `dump_and_migrate_schema.py` - Migration script
- `check_railway_extensions.py` - Extension checker
- `.env.backup` - Backup of original .env
