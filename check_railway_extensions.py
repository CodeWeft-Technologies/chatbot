"""
Check Railway PostgreSQL Extensions
"""
import psycopg

RAILWAY_DB_URL = "postgres://postgres:xcNBHaabpryqnEFg7RG_z2LDn6XxzMZY@maglev.proxy.rlwy.net:23238/railway"

try:
    conn = psycopg.connect(RAILWAY_DB_URL, autocommit=True)
    cursor = conn.cursor()
    
    print("=" * 80)
    print("CHECKING RAILWAY POSTGRESQL EXTENSIONS")
    print("=" * 80)
    
    # Check PostgreSQL version
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    print(f"\nPostgreSQL Version:\n  {version}\n")
    
    # Check available extensions
    print("Available Extensions:")
    cursor.execute("""
        SELECT name, default_version, comment
        FROM pg_available_extensions
        ORDER BY name;
    """)
    
    extensions = cursor.fetchall()
    for name, version, comment in extensions:
        print(f"  - {name:30} (v{version or 'N/A':10}) {comment or ''}")
    
    # Check installed extensions
    print("\n\nCurrently Installed Extensions:")
    cursor.execute("""
        SELECT extname, extversion
        FROM pg_extension
        ORDER BY extname;
    """)
    
    installed = cursor.fetchall()
    if installed:
        for name, version in installed:
            print(f"  - {name:30} (v{version})")
    else:
        print("  (No extensions currently installed)")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
