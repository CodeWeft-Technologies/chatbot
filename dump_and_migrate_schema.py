"""
Complete Schema Dump and Migration Script
Dumps actual schema from Supabase and applies it to Railway PostgreSQL
"""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

# Database URLs
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_DSN")
RAILWAY_DB_URL = "postgresql://postgres:xcNBHaabpryqnEFg7RG_z2LDn6XxzMZY@maglev.proxy.rlwy.net:23238/railway"

def get_supabase_source_url():
    """Determine the Supabase source DB URL, preferring a dedicated env or backup"""
    # 1) Explicit override via SUPABASE_SOURCE_DB_DSN
    src = os.getenv("SUPABASE_SOURCE_DB_DSN")
    if src:
        return src
    # 2) Try .env.backup for original value
    env_dir = os.path.dirname(__file__)
    backup_path = os.path.join(env_dir, '.env.backup')
    if os.path.exists(backup_path):
        try:
            with open(backup_path, 'r') as bf:
                for line in bf:
                    line = line.strip()
                    if line.startswith('SUPABASE_DB_DSN=') and not line.startswith('#'):
                        return line.split('=', 1)[1].strip()
        except Exception:
            pass
    # 3) Fallback to current SUPABASE_DB_DSN
    return SUPABASE_DB_URL

def dump_supabase_schema():
    """Dump the complete schema from Supabase including all tables, indexes, and functions"""
    print("=" * 80)
    print("DUMPING SCHEMA FROM SUPABASE")
    print("=" * 80)
    
    try:
        source_url = get_supabase_source_url()
        print(f"\nUsing source DB URL: {('' if not source_url else source_url[:60] + '...')}")
        conn = psycopg.connect(source_url)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n[OK] Found {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")
        
        # Get table definitions
        schema_sql = []
        
        schema_sql.append("-- ============================================")
        schema_sql.append("-- Complete Schema Dump from Supabase")
        schema_sql.append("-- Generated for Railway PostgreSQL Migration")
        schema_sql.append("-- ============================================\n")
        
        schema_sql.append("-- Enable required extensions")
        schema_sql.append("CREATE EXTENSION IF NOT EXISTS vector;")
        schema_sql.append("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";\n")
        
        for table in tables:
            print(f"\nDumping table: {table}")
            
            # Get table structure
            cursor.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    column_default,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' 
                AND table_name = '{table}'
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            
            schema_sql.append(f"\n-- Table: {table}")
            schema_sql.append(f"CREATE TABLE IF NOT EXISTS {table} (")
            
            col_defs = []
            for col in columns:
                col_name, data_type, max_len, default, nullable = col
                
                # Build column definition
                col_def = f"  {col_name} "
                
                # Handle data types
                if data_type == 'USER-DEFINED':
                    # Use format_type to capture full type details (e.g., vector(1024))
                    cursor.execute(f"""
                        SELECT pg_catalog.format_type(a.atttypid, a.atttypmod)
                        FROM pg_attribute a
                        WHERE a.attrelid = '{table}'::regclass AND a.attname = '{col_name}'
                    """)
                    fmt = cursor.fetchone()
                    if fmt and fmt[0]:
                        col_def += fmt[0].upper()
                    else:
                        # Fallback to udt_name
                        cursor.execute(f"""
                            SELECT udt_name FROM information_schema.columns 
                            WHERE table_name = '{table}' AND column_name = '{col_name}'
                        """)
                        udt = cursor.fetchone()
                        col_def += (udt[0].upper() if udt and udt[0] else data_type)
                elif data_type == 'ARRAY':
                    # Get the element type of the array
                    cursor.execute(f"""
                        SELECT data_type FROM information_schema.element_types
                        WHERE object_schema = 'public' 
                        AND object_name = '{table}'
                        AND collection_type_identifier LIKE '%%{col_name}%%'
                    """)
                    elem_type = cursor.fetchone()
                    if elem_type:
                        col_def += f"{elem_type[0].upper()}[]"
                    else:
                        col_def += "TEXT[]"  # Default to text array
                elif data_type == 'character varying':
                    col_def += "TEXT"
                elif data_type == 'timestamp with time zone':
                    col_def += "TIMESTAMPTZ"
                elif data_type == 'timestamp without time zone':
                    col_def += "TIMESTAMP"
                elif data_type == 'double precision':
                    col_def += "DOUBLE PRECISION"
                else:
                    col_def += data_type.upper()
                
                # Handle defaults
                if default:
                    # Clean up default value
                    default_val = default.replace("::character varying", "")
                    default_val = default_val.replace("::text", "")
                    if 'nextval' in default_val:
                        # It's a sequence (serial)
                        if 'BIGINT' in col_def or 'bigint' in data_type:
                            col_def = f"  {col_name} BIGSERIAL"
                            default = None
                        else:
                            col_def = f"  {col_name} SERIAL"
                            default = None
                    elif default_val:
                        col_def += f" DEFAULT {default_val}"
                
                # Handle nullability
                if nullable == 'NO':
                    col_def += " NOT NULL"
                
                col_defs.append(col_def)
            
            # Get primary key
            cursor.execute(f"""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = '{table}'::regclass AND i.indisprimary;
            """)
            pk_cols = [row[0] for row in cursor.fetchall()]
            if pk_cols:
                col_defs.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")
            
            # Get unique constraints
            cursor.execute(f"""
                SELECT
                    conname,
                    pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE contype = 'u' AND n.nspname = 'public' AND conrelid::regclass::text = '{table}'
            """)
            for constraint_name, constraint_def in cursor.fetchall():
                # Extract column names from constraint definition
                if 'UNIQUE' in constraint_def:
                    col_defs.append(f"  {constraint_def}")
            
            # Get check constraints
            cursor.execute(f"""
                SELECT
                    conname,
                    pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE contype = 'c' AND n.nspname = 'public' AND conrelid::regclass::text = '{table}'
            """)
            for constraint_name, constraint_def in cursor.fetchall():
                col_defs.append(f"  {constraint_def}")
            
            schema_sql.append(",\n".join(col_defs))
            schema_sql.append(");\n")
        
        # Get indexes
        schema_sql.append("\n-- ============================================")
        schema_sql.append("-- Indexes")
        schema_sql.append("-- ============================================\n")
        
        cursor.execute("""
            SELECT 
                schemaname,
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname NOT LIKE '%_pkey'
            ORDER BY tablename, indexname;
        """)
        
        for row in cursor.fetchall():
            schema, table, index_name, index_def = row
            # Ensure idempotent index creation for both regular and unique indexes
            if index_def.startswith("CREATE UNIQUE INDEX"):
                index_def = index_def.replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS")
            else:
                index_def = index_def.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS")
            schema_sql.append(index_def + ";")
        
        # Get functions
        schema_sql.append("\n-- ============================================")
        schema_sql.append("-- Functions")
        schema_sql.append("-- ============================================\n")
        
        cursor.execute("""
            SELECT 
                p.proname as function_name,
                pg_get_functiondef(p.oid) as function_def
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public'
            AND p.prokind = 'f'
            ORDER BY p.proname;
        """)
        
        for row in cursor.fetchall():
            func_name, func_def = row
            schema_sql.append(f"\n-- Function: {func_name}")
            schema_sql.append(func_def + ";")
        
        cursor.close()
        conn.close()
        
        # Write to file
        schema_file = os.path.join(os.path.dirname(__file__), 'railway_complete_schema.sql')
        with open(schema_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(schema_sql))
        
        print(f"\n[OK] Schema dumped to: {schema_file}")
        return schema_file
        
    except Exception as e:
        print(f"[ERROR] Failed to dump schema: {e}")
        import traceback
        traceback.print_exc()
        return None

def apply_to_railway(schema_file):
    """Apply the dumped schema to Railway database"""
    print("\n" + "=" * 80)
    print("APPLYING SCHEMA TO RAILWAY")
    print("=" * 80)
    
    try:
        # Test connection first
        print("\nTesting Railway connection...")
        conn = psycopg.connect(RAILWAY_DB_URL, autocommit=True)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"[OK] Connected to: {version[0][:50]}...")
        
        # Enable extensions first
        print("\nEnabling extensions...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        print("[OK] Extensions enabled")

        # Create compatibility shim for Supabase auth schema/functions used in RLS policies
        cursor.execute("CREATE SCHEMA IF NOT EXISTS auth;")
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION auth.uid()
            RETURNS uuid
            LANGUAGE sql
            STABLE
            AS $$
                SELECT null::uuid;
            $$;
            """
        )
        
        # Read and execute schema
        print(f"\nReading schema from: {schema_file}")
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        print("Applying schema...")
        cursor.execute(schema_sql)
        print("[OK] Schema applied successfully")
        
        # Verify tables
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        print(f"\n[OK] Verified {len(tables)} tables in Railway database:")
        for table in tables:
            print(f"  - {table}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to apply schema: {e}")
        import traceback
        traceback.print_exc()
        return False

def update_env_file():
    """Update .env file to use Railway database"""
    print("\n" + "=" * 80)
    print("UPDATING ENVIRONMENT CONFIGURATION")
    print("=" * 80)
    
    try:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        
        # Read current .env
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Create backup
        backup_path = env_path + '.backup'
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"✓ Created backup: {backup_path}")
        
        # Update SUPABASE_DB_DSN to use Railway
        lines = content.split('\n')
        new_lines = []
        updated = False
        
        for line in lines:
            if line.startswith('SUPABASE_DB_DSN='):
                new_lines.append('# Original Supabase DB (commented out)')
                new_lines.append('# ' + line)
                new_lines.append('')
                new_lines.append('# Railway Database (ACTIVE)')
                new_lines.append(f'SUPABASE_DB_DSN={RAILWAY_DB_URL}')
                updated = True
            else:
                new_lines.append(line)
        
        # Write updated .env
        with open(env_path, 'w') as f:
            f.write('\n'.join(new_lines))
        
        if updated:
            print("[OK] Updated .env file to use Railway database")
        else:
            print("[WARN] SUPABASE_DB_DSN not found in .env file")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update .env: {e}")
        return False

def main():
    """Main migration process"""
    print("\n")
    print("=" * 80)
    print("RAILWAY DATABASE MIGRATION")
    print("Complete Schema Dump and Migration Tool")
    print("=" * 80)
    print(f"\nSource: Supabase Database")
    print(f"Target: Railway Database")
    print("=" * 80)
    
    # Step 1: Dump schema from Supabase
    schema_file = dump_supabase_schema()
    if not schema_file:
        print("\n[WARN] Schema dump failed. Aborting migration.")
        return
    
    # Step 2: Apply to Railway
    if not apply_to_railway(schema_file):
        print("\n[WARN] Schema application failed. Check errors above.")
        return
    
    # Step 3: Update .env file
    update_env_file()
    
    print("\n" + "=" * 80)
    print("[OK] MIGRATION COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review the generated schema file: railway_complete_schema.sql")
    print("2. Test your application with Railway database")
    print("3. If needed, restore original config from .env.backup")
    print("\nRailway Database URL:")
    print(f"  {RAILWAY_DB_URL}")
    print("=" * 80)

if __name__ == "__main__":
    main()
