#!/usr/bin/env python3
"""
Sets up MySQL database, user, tables, seeds/migrates data, and configures .env for DSH-RAG on EC2.
"""
import os
import sys
import sqlite3
import pymysql
import subprocess
from pathlib import Path

import secrets
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("MYSQL_DATABASE", "rag_users")
DB_USER = os.getenv("MYSQL_USER", "rag_user")
DB_PASS = os.getenv("MYSQL_PASSWORD", "").strip() or secrets.token_urlsafe(18)
BASE_DIR = Path("/home/ubuntu/DSH-RAG")
SQLITE_PATH = BASE_DIR / "users_data.db"
ENV_PATH = BASE_DIR / ".env"

def main():
    print("=== [1/6] Connecting to MySQL via Unix Socket (Administrative) ===")
    try:
        root_conn = pymysql.connect(
            user="root",
            unix_socket="/var/run/mysqld/mysqld.sock",
            autocommit=True
        )
    except Exception as e:
        print(f"Failed to connect via /var/run/mysqld/mysqld.sock: {e}")
        sys.exit(1)

    print("=== [2/6] Creating database and dedicated application user ===")
    with root_conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        print(f"Database '{DB_NAME}' created or verified.")

        # Create or update user
        cur.execute(f"CREATE USER IF NOT EXISTS '{DB_USER}'@'localhost' IDENTIFIED BY '{DB_PASS}';")
        cur.execute(f"ALTER USER '{DB_USER}'@'localhost' IDENTIFIED BY '{DB_PASS}';")
        cur.execute(f"GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO '{DB_USER}'@'localhost';")
        cur.execute("FLUSH PRIVILEGES;")
        print(f"User '{DB_USER}'@'localhost' created and privileges granted.")
    root_conn.close()

    print("=== [3/6] Connecting with newly created application user ===")
    app_conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )
    print("Successfully connected to MySQL using new application credentials!")

    print("=== [4/6] Creating schema tables ===")
    with app_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                email VARCHAR(150) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL,
                item_type VARCHAR(50) NOT NULL,
                item_title VARCHAR(255) NOT NULL,
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_purchases (user_id),
                CONSTRAINT fk_purchases_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS past_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL,
                interaction_type VARCHAR(100) NOT NULL,
                summary_notes TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_records (user_id),
                CONSTRAINT fk_records_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_key VARCHAR(150) NOT NULL,
                user_id VARCHAR(100) NOT NULL,
                conversation_id VARCHAR(100) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content MEDIUMTEXT NOT NULL,
                topic VARCHAR(255),
                mode VARCHAR(50),
                created_at DOUBLE NOT NULL,
                INDEX idx_conv_session (session_key, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        print("Schema tables (users, purchases, past_records, conversation_turns) ready.")

    print("=== [5/6] Migrating existing SQLite data to MySQL ===")
    migrated_users = 0
    migrated_purchases = 0
    migrated_records = 0

    if SQLITE_PATH.exists():
        try:
            sq_conn = sqlite3.connect(str(SQLITE_PATH))
            sq_conn.row_factory = sqlite3.Row
            sq_cur = sq_conn.cursor()

            # Check if users table exists in SQLite
            sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if sq_cur.fetchone():
                sq_cur.execute("SELECT id, name, email FROM users")
                u_rows = sq_cur.fetchall()
                with app_conn.cursor() as cur:
                    for u in u_rows:
                        cur.execute(
                            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email)",
                            (u["id"], u["name"], u["email"])
                        )
                        migrated_users += 1

            # Check purchases
            sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purchases'")
            if sq_cur.fetchone():
                sq_cur.execute("SELECT user_id, item_type, item_title FROM purchases")
                p_rows = sq_cur.fetchall()
                with app_conn.cursor() as cur:
                    for p in p_rows:
                        cur.execute(
                            "SELECT id FROM purchases WHERE user_id=%s AND item_title=%s",
                            (p["user_id"], p["item_title"])
                        )
                        if not cur.fetchone():
                            cur.execute(
                                "INSERT INTO purchases (user_id, item_type, item_title) VALUES (%s, %s, %s)",
                                (p["user_id"], p["item_type"], p["item_title"])
                            )
                            migrated_purchases += 1

            # Check past_records
            sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='past_records'")
            if sq_cur.fetchone():
                sq_cur.execute("SELECT user_id, interaction_type, summary_notes FROM past_records")
                r_rows = sq_cur.fetchall()
                with app_conn.cursor() as cur:
                    for r in r_rows:
                        cur.execute(
                            "SELECT id FROM past_records WHERE user_id=%s AND summary_notes=%s",
                            (r["user_id"], r["summary_notes"])
                        )
                        if not cur.fetchone():
                            cur.execute(
                                "INSERT INTO past_records (user_id, interaction_type, summary_notes) VALUES (%s, %s, %s)",
                                (r["user_id"], r["interaction_type"], r["summary_notes"])
                            )
                            migrated_records += 1

            sq_conn.close()
            print(f"Migrated from SQLite: {migrated_users} users, {migrated_purchases} purchases, {migrated_records} records.")
        except Exception as e:
            print(f"Notice during SQLite migration: {e}")
    else:
        print("No users_data.db found, applying standard seed personas.")

    # Ensure John, Sarah, and Guest exist
    with app_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (id, name, email) VALUES
            ('john', 'John', 'john@example.com'),
            ('sarah', 'Sarah', 'sarah@example.com'),
            ('guest', 'Guest User', 'guest@example.com')
            ON DUPLICATE KEY UPDATE name=VALUES(name);
        """)
        cur.execute("""
            INSERT IGNORE INTO purchases (user_id, item_type, item_title) VALUES
            ('john', 'session', '55-minute ADHD session'),
            ('john', 'book', 'How to Be Calm When Having ADHD'),
            ('sarah', 'course', 'Mindfulness and Deep Focus Workshop'),
            ('sarah', 'book', 'Atomic Habits for Neurodiverse Minds');
        """)
        cur.execute("""
            INSERT IGNORE INTO past_records (user_id, interaction_type, summary_notes) VALUES
            ('sarah', 'Coaching Session', 'Discussed developing an energizing morning routine to reduce sensory overload and afternoon focus slump.');
        """)
    app_conn.close()
    print("Default seed personas (John, Sarah, Guest) verified.")

    print("=== [6/6] Updating .env configuration file on server ===")
    if ENV_PATH.exists():
        content = ENV_PATH.read_text(encoding="utf-8")
        
        # Helper to update or append key-value
        def set_kv(txt, key, val):
            import re
            pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
            if pattern.search(txt):
                return pattern.sub(f"{key}={val}", txt)
            else:
                return txt.strip() + f"\n{key}={val}\n"

        content = set_kv(content, "MYSQL_HOST", "127.0.0.1")
        content = set_kv(content, "MYSQL_PORT", "3306")
        content = set_kv(content, "MYSQL_USER", DB_USER)
        content = set_kv(content, "MYSQL_PASSWORD", DB_PASS)
        content = set_kv(content, "MYSQL_DATABASE", DB_NAME)
        ENV_PATH.write_text(content, encoding="utf-8")
        print(".env updated with active MySQL credentials.")
    else:
        print("Warning: .env not found at", ENV_PATH)

    print("\n>>> MySQL setup and migration completed successfully! <<<")

if __name__ == "__main__":
    main()
