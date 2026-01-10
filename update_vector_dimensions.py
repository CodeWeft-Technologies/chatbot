"""
Update vector dimensions from 1024 to 1536 for OpenAI embeddings.
This script will:
1. Drop the old embeddings table
2. Recreate it with vector(1536)
3. Recreate the index
"""
import psycopg
from app.config import settings

def update_dimensions():
    print("🔄 Updating vector dimensions from 1024 to 1536...")
    
    with psycopg.connect(settings.SUPABASE_DB_DSN) as conn:
        with conn.cursor() as cur:
            # Drop existing table (this will delete all embeddings)
            print("⚠️  Dropping old rag_embeddings table...")
            cur.execute("DROP TABLE IF EXISTS rag_embeddings CASCADE;")
            
            # Recreate with new dimensions
            print("✅ Creating rag_embeddings table with vector(1536)...")
            cur.execute("""
                CREATE TABLE rag_embeddings (
                    id SERIAL PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    bot_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding EXTENSIONS.vector(1536) NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create index for faster similarity search
            print("🔍 Creating vector similarity index...")
            cur.execute("""
                CREATE INDEX rag_embeddings_vector_idx 
                ON rag_embeddings 
                USING ivfflat (embedding)
                WITH (lists = 100);
            """)
            
            # Create additional indexes
            print("📊 Creating additional indexes...")
            cur.execute("CREATE INDEX rag_embeddings_org_bot_idx ON rag_embeddings(org_id, bot_id);")
            
            conn.commit()
            print("✅ Migration complete! Vector dimensions updated to 1536.")
            print("⚠️  Note: All previous embeddings have been deleted. You'll need to re-ingest your data.")

if __name__ == "__main__":
    update_dimensions()
