"""
Railway pgvector Installation Helper
Provides instructions and tools for installing pgvector on Railway PostgreSQL
"""

import psycopg
import json

RAILWAY_DB_URL = "postgres://postgres:xcNBHaabpryqnEFg7RG_z2LDn6XxzMZY@maglev.proxy.rlwy.net:23238/railway"

def check_superuser_access():
    """Check if we have superuser access to install extensions"""
    print("=" * 80)
    print("CHECKING DATABASE PERMISSIONS")
    print("=" * 80)
    
    try:
        conn = psycopg.connect(RAILWAY_DB_URL, autocommit=True)
        cursor = conn.cursor()
        
        # Check if current user is superuser
        cursor.execute("SELECT current_user, usesuper FROM pg_user WHERE usename = current_user;")
        user, is_super = cursor.fetchone()
        
        print(f"\nCurrent Database User: {user}")
        print(f"Superuser Privileges: {'✓ YES' if is_super else '✗ NO'}")
        
        if not is_super:
            print("\n⚠️  WARNING: You do not have superuser privileges.")
            print("   pgvector extension requires superuser access to install.")
            print("\n   Contact Railway support or use Railway's pgvector template.")
        
        cursor.close()
        conn.close()
        
        return is_super
        
    except Exception as e:
        print(f"✗ Error checking permissions: {e}")
        return False

def create_sql_install_script():
    """Create SQL script to install pgvector (if you have system access)"""
    script = """-- pgvector Installation Script for Railway PostgreSQL
-- This script should be run by a database administrator with system access

-- Note: pgvector must be installed at the system level first
-- Run these commands on the Railway PostgreSQL container:

/*
# SSH into Railway container (requires Railway CLI)
railway shell

# Install build dependencies
apt-get update
apt-get install -y git build-essential postgresql-server-dev-17

# Clone and build pgvector
cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
make install  # Requires root/sudo

# After installation, connect to database and run:
*/

-- Enable the extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- Test vector operations
CREATE TABLE IF NOT EXISTS vector_test (
    id SERIAL PRIMARY KEY,
    embedding vector(1024)
);

-- If this works, pgvector is installed correctly
INSERT INTO vector_test (embedding) VALUES ('[0,0,0,0]');

-- Clean up test
DROP TABLE vector_test;

SELECT 'pgvector installation successful!' as status;
"""
    
    with open('install_pgvector_railway.sql', 'w') as f:
        f.write(script)
    
    print("\n✓ Created SQL installation script: install_pgvector_railway.sql")
    return 'install_pgvector_railway.sql'

def create_docker_instructions():
    """Create instructions for Railway pgvector deployment"""
    instructions = """# Railway pgvector Deployment Options

## Option 1: Use Railway pgvector Template (EASIEST)

1. Go to Railway Dashboard: https://railway.app/dashboard
2. Create a new project
3. Search for "PostgreSQL with pgvector" template
4. Deploy the template
5. Copy the new database connection string
6. Update your .env file with the new connection

## Option 2: Request pgvector Installation (Contact Support)

1. Open a ticket with Railway support
2. Request pgvector extension installation
3. Provide your database service ID
4. Wait for support to install the extension

## Option 3: Self-Install via Railway CLI (Advanced)

### Prerequisites:
- Railway CLI installed: `npm install -g @railway/cli`
- Railway account logged in: `railway login`

### Steps:

```bash
# Link to your Railway project
railway link

# Open a shell in your PostgreSQL container
railway run --service postgres bash

# Install dependencies (inside container)
apt-get update
apt-get install -y git build-essential postgresql-server-dev-17

# Clone and build pgvector
cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector
make clean
make
make install

# Restart PostgreSQL service in Railway dashboard
# Then connect and create extension:
railway run --service postgres psql

# In psql:
CREATE EXTENSION vector;
\\dx vector
\\q
```

## Option 4: Deploy Custom Dockerfile (Full Control)

Create a custom Dockerfile for PostgreSQL with pgvector:

```dockerfile
FROM postgres:17

# Install build dependencies
RUN apt-get update && \\
    apt-get install -y \\
        git \\
        build-essential \\
        postgresql-server-dev-17 && \\
    rm -rf /var/lib/apt/lists/*

# Install pgvector
RUN cd /tmp && \\
    git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git && \\
    cd pgvector && \\
    make clean && \\
    make OPTFLAGS="" && \\
    make install && \\
    rm -rf /tmp/pgvector

# Cleanup
RUN apt-get remove -y git build-essential && \\
    apt-get autoremove -y
```

Then deploy to Railway:

1. Create a new service in Railway
2. Connect your GitHub repo with this Dockerfile
3. Railway will build and deploy automatically
4. Get the connection string from Railway dashboard

## Verification

After installation, verify pgvector is working:

```sql
-- Connect to your database
CREATE EXTENSION IF NOT EXISTS vector;

-- Check extension is available
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- Test vector operations
CREATE TABLE test_vectors (id serial PRIMARY KEY, embedding vector(3));
INSERT INTO test_vectors (embedding) VALUES ('[1,2,3]'), ('[4,5,6]');
SELECT embedding <-> '[3,3,3]' AS distance FROM test_vectors ORDER BY distance;
DROP TABLE test_vectors;
```

## Need Help?

- Railway Discord: https://discord.gg/railway
- Railway Docs: https://docs.railway.app/
- pgvector GitHub: https://github.com/pgvector/pgvector
"""
    
    with open('RAILWAY_PGVECTOR_SETUP.md', 'w') as f:
        f.write(instructions)
    
    print("✓ Created setup instructions: RAILWAY_PGVECTOR_SETUP.md")
    return 'RAILWAY_PGVECTOR_SETUP.md'

def create_alternative_schema():
    """Create schema that works without pgvector (using JSONB for embeddings)"""
    schema = """-- Alternative Schema for Railway (Without pgvector)
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
"""
    
    with open('railway_schema_without_vector.sql', 'w') as f:
        f.write(schema)
    
    print("✓ Created alternative schema: railway_schema_without_vector.sql")
    return 'railway_schema_without_vector.sql'

def main():
    print("\n")
    print("=" * 80)
    print("RAILWAY PGVECTOR INSTALLATION HELPER")
    print("=" * 80)
    
    # Check superuser access
    has_super = check_superuser_access()
    
    print("\n\n" + "=" * 80)
    print("CREATING HELPER FILES")
    print("=" * 80)
    
    # Create helper files
    sql_file = create_sql_install_script()
    docs_file = create_docker_instructions()
    alt_schema = create_alternative_schema()
    
    print("\n\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    
    if has_super:
        print("\n✓ You have superuser access!")
        print(f"\n1. Review: {sql_file}")
        print("2. Install pgvector on the Railway container")
        print("3. Run the migration script again")
    else:
        print("\n⚠️  No superuser access detected.")
        print("\nChoose one of these options:")
        print(f"\n1. EASIEST: Use Railway's pgvector template")
        print(f"   → See instructions in: {docs_file}")
        print(f"\n2. WORKAROUND: Use JSONB for embeddings (slower)")
        print(f"   → Schema available in: {alt_schema}")
        print(f"\n3. HYBRID: Keep Supabase for embeddings, Railway for other data")
        print(f"   → Modify app to use two database connections")
    
    print("\n" + "=" * 80)
    print("Files Created:")
    print(f"  - {sql_file}")
    print(f"  - {docs_file}")
    print(f"  - {alt_schema}")
    print("=" * 80)

if __name__ == "__main__":
    main()
