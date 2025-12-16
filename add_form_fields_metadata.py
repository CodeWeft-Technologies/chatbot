"""
Migration script to add metadata column to form_fields table
This allows storing form_type (booking/reschedule) and other metadata
"""

from app.db import get_conn

def add_metadata_column():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check if metadata column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'form_fields' 
                AND column_name = 'metadata'
            """)
            
            if cur.fetchone():
                print("✓ metadata column already exists")
            else:
                # Add metadata column
                cur.execute("""
                    ALTER TABLE form_fields 
                    ADD COLUMN metadata jsonb DEFAULT '{}'::jsonb
                """)
                conn.commit()
                print("✓ Added metadata column to form_fields table")
                
        conn.close()
        print("✓ Migration completed successfully")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
        conn.close()

if __name__ == "__main__":
    add_metadata_column()
