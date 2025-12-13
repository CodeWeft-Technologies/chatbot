#!/usr/bin/env python
"""Migration script to add external_event_id column to bookings table"""

import sys
sys.path.insert(0, '.')

from app.db import get_conn

def main():
    print("Running migration: Add external_event_id column to bookings table")
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Add external_event_id column if it doesn't exist
            cur.execute("""
                ALTER TABLE bookings 
                ADD COLUMN IF NOT EXISTS external_event_id text
            """)
            
            # Copy data from calendar_event_id if it exists
            cur.execute("""
                UPDATE bookings 
                SET external_event_id = calendar_event_id 
                WHERE calendar_event_id IS NOT NULL 
                AND external_event_id IS NULL
            """)
            
            conn.commit()
            print("✓ Migration successful: external_event_id column added to bookings table")
            
            # Verify the column was added
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'bookings' 
                AND column_name = 'external_event_id'
            """)
            result = cur.fetchone()
            if result:
                print(f"✓ Verified: Column 'external_event_id' exists with type '{result[1]}'")
            else:
                print("⚠️ Warning: Could not verify column creation")
                
    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()
    
    print("\nMigration complete!")

if __name__ == "__main__":
    main()
