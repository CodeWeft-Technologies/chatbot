"""
Quick Database URL Updater
Updates the Railway database URL in the migration script
"""

import os
import re

def update_railway_url():
    """Interactive script to update Railway database URL"""
    print("=" * 80)
    print("RAILWAY DATABASE URL UPDATER")
    print("=" * 80)
    
    print("\n📋 Instructions:")
    print("1. Deploy Railway's pgvector template from the dashboard")
    print("2. Copy the Postgres Connection URL")
    print("3. Paste it here when prompted")
    print("\n" + "=" * 80)
    
    # Get new URL from user
    print("\n🔗 Enter your NEW Railway pgvector database URL:")
    print("   (Format: postgresql://postgres:password@host:port/database)")
    new_url = input("\n   URL: ").strip()
    
    if not new_url.startswith("postgresql://"):
        print("\n❌ Invalid URL format. Should start with 'postgresql://'")
        return
    
    # Confirm
    print(f"\n✅ New URL: {new_url[:50]}...")
    confirm = input("\n   Update migration script? (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y']:
        print("\n❌ Cancelled.")
        return
    
    # Update dump_and_migrate_schema.py
    script_path = os.path.join(os.path.dirname(__file__), 'dump_and_migrate_schema.py')
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace the RAILWAY_DB_URL line
        pattern = r'RAILWAY_DB_URL = "postgresql://[^"]+?"'
        replacement = f'RAILWAY_DB_URL = "{new_url}"'
        
        new_content = re.sub(pattern, replacement, content)
        
        # Write back
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("\n✅ Updated: dump_and_migrate_schema.py")
        
    except Exception as e:
        print(f"\n❌ Error updating dump_and_migrate_schema.py: {e}")
        return
    
    # Update check_railway_extensions.py
    check_script = os.path.join(os.path.dirname(__file__), 'check_railway_extensions.py')
    
    try:
        with open(check_script, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = re.sub(pattern, replacement, content)
        
        with open(check_script, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ Updated: check_railway_extensions.py")
        
    except Exception as e:
        print(f"⚠️  Warning: Could not update check_railway_extensions.py: {e}")
    
    # Update setup_pgvector_railway.py
    setup_script = os.path.join(os.path.dirname(__file__), 'setup_pgvector_railway.py')
    
    try:
        with open(setup_script, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = re.sub(pattern, replacement, content)
        
        with open(setup_script, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ Updated: setup_pgvector_railway.py")
        
    except Exception as e:
        print(f"⚠️  Warning: Could not update setup_pgvector_railway.py: {e}")
    
    print("\n" + "=" * 80)
    print("🎉 DATABASE URL UPDATED SUCCESSFULLY!")
    print("=" * 80)
    print("\n📋 Next Steps:")
    print("1. Run: python dump_and_migrate_schema.py")
    print("2. The migration will use your new pgvector database")
    print("3. All 22 tables will be created automatically")
    print("\n" + "=" * 80)

def show_current_url():
    """Show the current Railway URL in the migration script"""
    script_path = os.path.join(os.path.dirname(__file__), 'dump_and_migrate_schema.py')
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'RAILWAY_DB_URL = "(postgresql://[^"]+)"', content)
        if match:
            url = match.group(1)
            # Mask the password
            masked = re.sub(r':([^@]+)@', ':****@', url)
            print(f"\n📍 Current Railway URL: {masked}")
        else:
            print("\n⚠️  Could not find RAILWAY_DB_URL in script")
            
    except Exception as e:
        print(f"\n❌ Error reading script: {e}")

if __name__ == "__main__":
    show_current_url()
    print()
    update_railway_url()
