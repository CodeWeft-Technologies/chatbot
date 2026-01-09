"""
Get Railway Database URL from Environment Variables
"""
import os

# Your Railway pgvector credentials
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "xcNBHaabpryqnEFg7RG_z2LDn6XxzMZY"
POSTGRES_DB = "railway"

print("=" * 80)
print("RAILWAY PGVECTOR DATABASE - CONNECTION INFO")
print("=" * 80)

print("\n📋 Your Railway pgvector database credentials:")
print(f"  User: {POSTGRES_USER}")
print(f"  Password: {POSTGRES_PASSWORD}")
print(f"  Database: {POSTGRES_DB}")

print("\n" + "=" * 80)
print("⚠️  IMPORTANT: Get the complete DATABASE_URL from Railway")
print("=" * 80)

print("\nTo get your complete DATABASE_URL:")
print("1. Go to Railway Dashboard")
print("2. Click on your PostgreSQL (pgvector) service")
print("3. Go to 'Variables' or 'Connect' tab")
print("4. Copy the DATABASE_URL value")
print("   It should look like:")
print("   postgresql://postgres:xcNBH...@xxx.railway.app:5432/railway")

print("\n" + "=" * 80)
print("QUICK SETUP")
print("=" * 80)

print("\nOnce you have the DATABASE_URL, run:")
print("  python update_railway_url.py")
print("\nThen paste your DATABASE_URL when prompted.")

print("\nOR manually update dump_and_migrate_schema.py:")
print("  Find: RAILWAY_DB_URL = \"postgresql://...")
print("  Replace with your new DATABASE_URL")

print("\n" + "=" * 80)
print("EXPECTED FORMAT")
print("=" * 80)

# Try to construct it (though we need the domain/port)
print("\nYour DATABASE_URL should be similar to:")
print(f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@[YOUR-PROJECT].railway.app:5432/{POSTGRES_DB}")
print("\n(The actual domain will be provided by Railway)")

print("\n" + "=" * 80)
