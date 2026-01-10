import psycopg
from app.config import settings

conn = psycopg.connect(settings.SUPABASE_DB_DSN)
cur = conn.cursor()

# Check all schemas
cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'embeddings';")
tables = cur.fetchall()
print(f"Found embeddings tables: {tables}")

# Check column info
cur.execute("""
    SELECT column_name, data_type, udt_name 
    FROM information_schema.columns 
    WHERE table_name = 'embeddings' 
    ORDER BY ordinal_position;
""")
columns = cur.fetchall()
print("\nColumns:")
for col in columns:
    print(f"  {col[0]}: {col[1]} ({col[2]})")

# Check vector type details
cur.execute("""
    SELECT 
        a.attname,
        pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type
    FROM pg_catalog.pg_attribute a
    WHERE a.attrelid = 'embeddings'::regclass
    AND a.attnum > 0 
    AND NOT a.attisdropped
    ORDER BY a.attnum;
""")
attrs = cur.fetchall()
print("\nActual types:")
for attr in attrs:
    print(f"  {attr[0]}: {attr[1]}")

conn.close()
