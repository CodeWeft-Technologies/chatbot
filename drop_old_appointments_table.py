#!/usr/bin/env python
"""Migration script to drop the old bot_appointments table"""

import sys
sys.path.insert(0, '.')

from app.db import get_conn

def main():
    print("Running migration: Drop old bot_appointments table")
    print("⚠️  WARNING: This will permanently delete the bot_appointments table and all its data!")
    print("   The new 'bookings' table is now used for all appointments.")
    
    response = input("\nAre you sure you want to proceed? Type 'yes' to confirm: ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        sys.exit(0)
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Drop the old bot_appointments table
            cur.execute("""
                DROP TABLE IF EXISTS bot_appointments CASCADE
            """)
            conn.commit()
            print("✓ Successfully dropped bot_appointments table")
            
            # Verify the table was dropped
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'bot_appointments'
            """)
            result = cur.fetchone()
            if not result:
                print("✓ Verified: bot_appointments table no longer exists")
            else:
                print("⚠️ Warning: Table still exists in database")
                
    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()
    
    print("\n✓ Migration complete!")
    print("  The system now uses only the 'bookings' table for all appointments.")

if __name__ == "__main__":
    main()
