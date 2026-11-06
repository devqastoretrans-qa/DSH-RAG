"""
Database Migration & Backfill Script: Chat History User Isolation & Privacy.

1. Ensures `is_orphaned` and `owner_status` columns exist on `conversation_turns`.
2. Backfills and flags all legacy unowned/guest records (`user_id` IS NULL, empty, or 'guest')
   with `is_orphaned = 1`, so they are never exposed to any authenticated user.
3. Ensures valid customer records have `is_orphaned = 0` and `owner_status = 'verified'`.
4. Creates composite indices on `(user_id, created_at)` and `(user_id, conversation_id)` for high-performance scoped lookups.
"""
import os
import sys
import sqlite3
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")


def migrate_sqlite(db_path: str = "users_data.db"):
    logger.info(f"--- Starting SQLite Migration on {db_path} ---")
    if not os.path.exists(db_path):
        logger.warning(f"SQLite DB file {db_path} does not exist. Skipping.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Check existing columns
    cur.execute("PRAGMA table_info(conversation_turns)")
    columns = [col[1] for col in cur.fetchall()]
    logger.info(f"Existing columns in SQLite conversation_turns: {columns}")

    if "is_orphaned" not in columns:
        logger.info("Adding column 'is_orphaned' to conversation_turns...")
        cur.execute("ALTER TABLE conversation_turns ADD COLUMN is_orphaned INTEGER NOT NULL DEFAULT 0")

    if "owner_status" not in columns:
        logger.info("Adding column 'owner_status' to conversation_turns...")
        cur.execute("ALTER TABLE conversation_turns ADD COLUMN owner_status TEXT NOT NULL DEFAULT 'verified'")

    # 2. Backfill unowned / guest records
    logger.info("Flagging legacy unowned and guest turns...")
    cur.execute("""
        UPDATE conversation_turns
        SET is_orphaned = 1, owner_status = 'unowned_legacy'
        WHERE user_id IS NULL OR TRIM(user_id) = '' OR LOWER(TRIM(user_id)) IN ('guest', 'none', 'null')
    """)
    flagged_count = cur.rowcount
    logger.info(f"Flagged {flagged_count} legacy/guest rows as orphaned.")

    # 3. Ensure valid user records are verified
    cur.execute("""
        UPDATE conversation_turns
        SET is_orphaned = 0, owner_status = 'verified'
        WHERE user_id IS NOT NULL AND TRIM(user_id) != '' AND LOWER(TRIM(user_id)) NOT IN ('guest', 'none', 'null')
    """)
    verified_count = cur.rowcount
    logger.info(f"Verified {verified_count} owned user conversation rows.")

    # 4. Create composite indices
    logger.info("Creating index idx_conv_user_created (user_id, created_at)...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_created ON conversation_turns (user_id, created_at)")

    logger.info("Creating index idx_conv_user_session (user_id, conversation_id)...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_session ON conversation_turns (user_id, conversation_id)")

    conn.commit()

    # Audit summary
    cur.execute("SELECT owner_status, is_orphaned, COUNT(*) FROM conversation_turns GROUP BY owner_status, is_orphaned")
    summary = cur.fetchall()
    logger.info(f"SQLite Migration Complete. Breakdown: {summary}")
    conn.close()


def migrate_mysql():
    logger.info("--- Starting MySQL Migration ---")
    try:
        import pymysql
    except ImportError:
        logger.warning("pymysql not installed. Skipping MySQL migration.")
        return

    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "rag_user")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "rag_users")

    if not password:
        logger.info("No MySQL password configured. Skipping MySQL migration.")
        return

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5
        )
    except Exception as e:
        logger.warning(f"Could not connect to MySQL: {e}. Skipping.")
        return

    with conn.cursor() as cur:
        # Check columns
        cur.execute("DESCRIBE conversation_turns")
        cols = [r[0] for r in cur.fetchall()]

        if "is_orphaned" not in cols:
            logger.info("Adding column 'is_orphaned' to MySQL conversation_turns...")
            cur.execute("ALTER TABLE conversation_turns ADD COLUMN is_orphaned INT NOT NULL DEFAULT 0")

        if "owner_status" not in cols:
            logger.info("Adding column 'owner_status' to MySQL conversation_turns...")
            cur.execute("ALTER TABLE conversation_turns ADD COLUMN owner_status VARCHAR(20) NOT NULL DEFAULT 'verified'")

        # Backfill
        cur.execute("""
            UPDATE conversation_turns
            SET is_orphaned = 1, owner_status = 'unowned_legacy'
            WHERE user_id IS NULL OR TRIM(user_id) = '' OR LOWER(TRIM(user_id)) IN ('guest', 'none', 'null')
        """)
        flagged = cur.rowcount
        logger.info(f"MySQL: Flagged {flagged} unowned/guest records as orphaned.")

        cur.execute("""
            UPDATE conversation_turns
            SET is_orphaned = 0, owner_status = 'verified'
            WHERE user_id IS NOT NULL AND TRIM(user_id) != '' AND LOWER(TRIM(user_id)) NOT IN ('guest', 'none', 'null')
        """)
        verified = cur.rowcount
        logger.info(f"MySQL: Verified {verified} user records.")

        # Indices
        try:
            cur.execute("CREATE INDEX idx_conv_user_created ON conversation_turns (user_id, created_at)")
            logger.info("MySQL: Created index idx_conv_user_created.")
        except Exception:
            pass

        try:
            cur.execute("CREATE INDEX idx_conv_user_session ON conversation_turns (user_id, conversation_id)")
            logger.info("MySQL: Created index idx_conv_user_session.")
        except Exception:
            pass

        conn.commit()

        cur.execute("SELECT owner_status, is_orphaned, COUNT(*) FROM conversation_turns GROUP BY owner_status, is_orphaned")
        logger.info(f"MySQL Migration Complete. Breakdown: {cur.fetchall()}")

    conn.close()


if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "users_data.db"
    migrate_sqlite(db_file)
    migrate_mysql()
