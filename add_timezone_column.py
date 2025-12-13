#!/usr/bin/env python
"""Migration script to add timezone column to bot_calendar_oauth table"""

import sys
sys.path.insert(0, '.')

from app.db import get_conn

def main():
    print("Running migration: Add timezone column to bot_calendar_oauth")
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Add timezone column if it doesn't exist
            cur.execute("""
                ALTER TABLE bot_calendar_oauth 
                ADD COLUMN IF NOT EXISTS timezone text
            """)
            conn.commit()
            print("✓ Migration successful: timezone column added to bot_calendar_oauth")
            
            # Verify the column was added
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'bot_calendar_oauth' 
                AND column_name = 'timezone'
            """)
            result = cur.fetchone()
            if result:
                print(f"✓ Verified: Column 'timezone' exists with type '{result[1]}'")
            else:
                print("⚠️ Warning: Could not verify column creation")
                
    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()
    
    print("\nMigration complete! You can now save timezone settings.")

if __name__ == "__main__":
    main()
