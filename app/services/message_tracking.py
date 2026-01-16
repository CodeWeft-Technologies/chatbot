"""
Message tracking service for billing and usage analytics.
Tracks ONLY user messages (questions sent) for billing purposes.
Each user message implies a bot response, so we count user interactions only.
"""
from typing import Optional
import psycopg
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def ensure_message_logs_table(conn):
    """Create user_message_logs table if it doesn't exist - ONLY tracks user messages for billing"""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_message_logs (
              id BIGSERIAL PRIMARY KEY,
              org_id TEXT NOT NULL,
              bot_id TEXT NOT NULL,
              session_id TEXT,
              created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        
        # Create indexes for performance
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_msg_org_bot ON user_message_logs(org_id, bot_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_msg_session ON user_message_logs(session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_msg_created ON user_message_logs(created_at)")
        except Exception as e:
            logger.debug(f"Index creation error (likely already exists): {e}")


def log_user_message(
    conn,
    org_id: str,
    bot_id: str,
    session_id: Optional[str] = None,
):
    """
    Log a user message (question sent to bot) for billing.
    
    Each user message = 1 interaction that will be charged.
    Bot may respond with content, template, or API integration - doesn't matter.
    We only count the USER MESSAGE = 1 billable event.
    
    Args:
        conn: Database connection
        org_id: Organization ID
        bot_id: Bot ID
        session_id: Conversation session ID (optional, for grouping)
    """
    from app.db import normalize_org_id, normalize_bot_id
    
    try:
        ensure_message_logs_table(conn)
        org_n = normalize_org_id(org_id)
        bot_n = normalize_bot_id(bot_id)
        
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_message_logs 
                (org_id, bot_id, session_id)
                VALUES (%s, %s, %s)
                """,
                (org_n, bot_n, session_id)
            )
        logger.debug(f"Logged user message for {org_n}/{bot_n}")
    except Exception as e:
        logger.error(f"Error logging user message: {e}")


def get_message_usage_stats(
    conn,
    org_id: str,
    bot_id: Optional[str] = None,
    days: int = 30,
):
    """
    Get user message (interaction) usage statistics for billing.
    Only counts USER MESSAGES (what customers are charged for).
    
    Returns:
    {
        "period": "last 30 days",
        "total_messages": 1250,            # Only user messages (billable interactions)
        "daily_breakdown": [...]
    }
    """
    from app.db import normalize_org_id, normalize_bot_id
    from datetime import timedelta
    
    try:
        ensure_message_logs_table(conn)
        org_n = normalize_org_id(org_id)
        
        with conn.cursor() as cur:
            # Build query based on bot_id
            if bot_id:
                bot_n = normalize_bot_id(bot_id)
                where_clause = "WHERE org_id=%s AND bot_id=%s AND created_at > NOW() - INTERVAL '%s days'"
                params = (org_n, bot_n, days)
            else:
                where_clause = "WHERE org_id=%s AND created_at > NOW() - INTERVAL '%s days'"
                params = (org_n, days)
            
            # Get overall stats (ONLY USER MESSAGES)
            cur.execute(
                f"""
                SELECT 
                  COUNT(*) as total_messages,
                  MIN(created_at) as first_message,
                  MAX(created_at) as last_message
                FROM user_message_logs
                {where_clause}
                """,
                params
            )
            
            row = cur.fetchone()
            if not row or row[0] == 0:  # No messages
                return {
                    "period": f"last {days} days",
                    "total_messages": 0,
                    "daily_breakdown": [],
                }
            
            total_messages = row[0] or 0
            
            # Get daily breakdown
            cur.execute(
                f"""
                SELECT 
                  DATE(created_at) as day,
                  COUNT(*) as messages
                FROM user_message_logs
                {where_clause}
                GROUP BY DATE(created_at)
                ORDER BY day DESC
                """,
                params
            )
            
            daily_breakdown = []
            for row_daily in cur.fetchall():
                daily_breakdown.append({
                    "date": row_daily[0].isoformat() if row_daily[0] else None,
                    "messages": row_daily[1] or 0,
                })
            
            return {
                "period": f"last {days} days",
                "total_messages": int(total_messages),      # This is what you charge for
                "daily_breakdown": daily_breakdown,
            }
    except Exception as e:
        logger.error(f"Error getting message usage stats: {e}")
        return {
            "error": str(e),
            "period": f"last {days} days",
            "total_messages": 0,
        }
