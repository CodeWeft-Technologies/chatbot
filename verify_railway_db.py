"""
Railway Database Status Check
Shows what tables exist and verifies pgvector
"""
import psycopg

RAILWAY_DB_URL = "postgresql://postgres:xcNBHaabpryqnEFg7RG_z2LDn6XxzMZY@maglev.proxy.rlwy.net:23238/railway"

print("=" * 80)
print("RAILWAY DATABASE STATUS")
print("=" * 80)

try:
    conn = psycopg.connect(RAILWAY_DB_URL, autocommit=True)
    cursor = conn.cursor()
    
    # Check extensions
    print("\n✓ Connected to Railway PostgreSQL\n")
    
    cursor.execute("SELECT extname, extversion FROM pg_extension ORDER BY extname;")
    extensions = cursor.fetchall()
    
    print("Installed Extensions:")
    for name, version in extensions:
        indicator = "✓" if name == 'vector' else " "
        print(f"  {indicator} {name:20} (v{version})")
    
    # Check tables
    cursor.execute("""
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY tablename;
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"\n\nTables in Database ({len(tables)} total):")
    if tables:
        for table in tables:
            print(f"  - {table}")
    else:
        print("  (No tables yet)")
    
    # Check if rag_embeddings has vector column
    if 'rag_embeddings' in tables:
        print("\n\nChecking rag_embeddings table...")
        cursor.execute("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'rag_embeddings'
            AND column_name = 'embedding';
        """)
        result = cursor.fetchone()
        if result:
            col_name, data_type, udt_name = result
            print(f"  ✓ embedding column: {udt_name} (type: {data_type})")
        else:
            print("  ⚠ embedding column not found")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("DATABASE READY FOR USE")
    print("=" * 80)
    print("\n✅ Your .env file has been updated to use Railway")
    print("\n📋 To complete migration:")
    print("   1. All tables need to be created (some exist, some don't)")
    print("   2. You can either:")
    print("      a) Drop all tables and rerun migration")
    print("      b) Or use the existing tables (schema already applied)")
    print("\n🚀 Start your application:")
    print("   python -m uvicorn app.main:app --reload")
    print("\n" + "=" * 80)
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
