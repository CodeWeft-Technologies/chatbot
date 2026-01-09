"""
Railway Database Migration Script
Applies the complete schema to Railway PostgreSQL database
"""
import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Railway database connection string
RAILWAY_DB_URL = "postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway"

def test_connection():
    """Test database connection"""
    print("Testing Railway database connection...")
    try:
        conn = psycopg2.connect(RAILWAY_DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✓ Successfully connected to PostgreSQL: {version[0]}")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def enable_extensions():
    """Enable required PostgreSQL extensions"""
    print("\nEnabling required extensions...")
    try:
        conn = psycopg2.connect(RAILWAY_DB_URL)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Enable vector extension for embeddings
        print("  - Enabling vector extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("    ✓ Vector extension enabled")
        
        # Enable uuid-ossp for UUID generation
        print("  - Enabling uuid-ossp extension...")
        cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        print("    ✓ UUID-OSSP extension enabled")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Failed to enable extensions: {e}")
        return False

def apply_migration():
    """Apply the migration SQL script"""
    print("\nApplying database migration...")
    try:
        # Read the migration file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        migration_file = os.path.join(script_dir, 'railway_migration.sql')
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        # Connect and execute
        conn = psycopg2.connect(RAILWAY_DB_URL)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("  - Executing migration script...")
        cursor.execute(migration_sql)
        print("    ✓ Migration completed successfully")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_schema():
    """Verify that tables were created"""
    print("\nVerifying schema...")
    try:
        conn = psycopg2.connect(RAILWAY_DB_URL)
        cursor = conn.cursor()
        
        # Check for key tables
        tables_to_check = [
            'organizations', 'app_users', 'chatbots', 'rag_embeddings',
            'conversations', 'form_configurations', 'form_fields',
            'booking_resources', 'resource_schedules', 'bookings',
            'bot_appointments', 'booking_audit_logs', 'booking_notifications'
        ]
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        print(f"  Found {len(existing_tables)} tables:")
        for table in existing_tables:
            status = "✓" if table in tables_to_check else " "
            print(f"    {status} {table}")
        
        # Check for vector extension
        cursor.execute("""
            SELECT extname 
            FROM pg_extension 
            WHERE extname = 'vector';
        """)
        has_vector = cursor.fetchone() is not None
        
        if has_vector:
            print("  ✓ Vector extension is installed")
        else:
            print("  ✗ Vector extension is NOT installed")
        
        # Check for sample data in form_templates
        cursor.execute("SELECT COUNT(*) FROM form_templates;")
        template_count = cursor.fetchone()[0]
        print(f"  ✓ {template_count} form templates inserted")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False

def update_env_file():
    """Update .env file with Railway database configuration"""
    print("\nUpdating .env file...")
    try:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        
        # Read current .env
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Add or update Railway DB URL
        railway_line = f"RAILWAY_DB_URL={RAILWAY_DB_URL}\n"
        db_url_line = f"DATABASE_URL={RAILWAY_DB_URL}\n"
        
        # Check if RAILWAY_DB_URL or DATABASE_URL already exists
        has_railway_url = any(line.startswith('RAILWAY_DB_URL=') for line in lines)
        has_db_url = any(line.startswith('DATABASE_URL=') for line in lines)
        
        if not has_railway_url:
            lines.append('\n# Railway Database Configuration\n')
            lines.append(railway_line)
            print("  ✓ Added RAILWAY_DB_URL to .env")
        
        if not has_db_url:
            lines.append(db_url_line)
            print("  ✓ Added DATABASE_URL to .env")
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(lines)
        
        print("  ✓ .env file updated")
        return True
    except Exception as e:
        print(f"✗ Failed to update .env: {e}")
        return False

def main():
    """Main migration process"""
    print("=" * 60)
    print("Railway Database Migration")
    print("=" * 60)
    
    # Step 1: Test connection
    if not test_connection():
        print("\n⚠ Please check your Railway database URL and try again")
        return
    
    # Step 2: Enable extensions
    if not enable_extensions():
        print("\n⚠ Failed to enable extensions. Continuing anyway...")
    
    # Step 3: Apply migration
    if not apply_migration():
        print("\n⚠ Migration failed. Please check the errors above.")
        return
    
    # Step 4: Verify schema
    if not verify_schema():
        print("\n⚠ Schema verification had issues. Please check manually.")
        return
    
    # Step 5: Update .env file
    update_env_file()
    
    print("\n" + "=" * 60)
    print("✓ Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Update your app to use Railway database by setting:")
    print("   DATABASE_URL or RAILWAY_DB_URL in your environment")
    print("2. Test your application functions")
    print("3. If using both databases, ensure data sync if needed")
    print("\nRailway Database URL:")
    print(f"  {RAILWAY_DB_URL}")

if __name__ == "__main__":
    main()
