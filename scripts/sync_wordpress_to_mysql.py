#!/usr/bin/env python3
"""
=============================================================================
Doctor Sarah Hensley AI (DSH-RAG) - WordPress / WooCommerce to MySQL Sync Tool
=============================================================================
Extracts customers and completed orders from WordPress WooCommerce REST API
and synchronizes clean, relevant records into local MySQL (rag_users).

Features:
  1. Selective Extraction: Extracts ONLY customer name, email, purchased items,
     and order dates. Excludes billing addresses, credit card data, and passwords.
  2. Idempotent & Non-Destructive: Uses ON DUPLICATE KEY UPDATE so it can be run
     repeatedly without creating duplicates or wiping existing history.
  3. Automatic Categorization: Categorizes products as 'session', 'course', or 'book'.
  4. Dual-Key Indexing: Maps both WooCommerce numeric customer ID and customer email
     so either can be passed to the RAG API.
  5. Dry-Run Mode: Pass --dry-run to test and preview without modifying the database.
=============================================================================
"""

import os
import sys
import argparse
import logging
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SYNC_LOG_FILE = LOGS_DIR / "sync.log"

file_handler = logging.FileHandler(str(SYNC_LOG_FILE), encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, file_handler]
)
logger = logging.getLogger("wp_mysql_sync")


class WordPressToMySQLSyncer:
    def __init__(self, dry_run: bool = False, max_pages: Optional[int] = None):
        self.dry_run = dry_run
        self.max_pages = max_pages

        # WordPress Configuration
        self.wp_url = os.getenv("WORDPRESS_URL", "").strip().rstrip("/")
        self.wp_user = os.getenv("WORDPRESS_USER", "").strip()
        self.wp_password = os.getenv("WORDPRESS_APP_PASSWORD", "").strip()
        self.ssl_verify = os.getenv("WP_SSL_VERIFY", "true").strip().lower() in ("true", "1", "yes")

        # MySQL Configuration
        self.mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
        self.mysql_port = int(os.getenv("MYSQL_PORT", 3306))
        self.mysql_user = os.getenv("MYSQL_USER", "rag_user").strip()
        self.mysql_password = os.getenv("MYSQL_PASSWORD", "").strip()
        self.mysql_db = os.getenv("MYSQL_DATABASE", "rag_users").strip()

        self._validate_env()

    def _validate_env(self):
        if not self.wp_url or not self.wp_user or not self.wp_password:
            logger.error("Missing WordPress credentials in .env (WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_APP_PASSWORD).")
            sys.exit(1)

        if not PYMYSQL_AVAILABLE and not self.dry_run:
            logger.error("PyMySQL is not installed. Please run: pip install pymysql")
            sys.exit(1)

    def _get_mysql_conn(self):
        return pymysql.connect(
            host=self.mysql_host,
            port=self.mysql_port,
            user=self.mysql_user,
            password=self.mysql_password,
            database=self.mysql_db,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor
        )

    def _classify_item(self, item_name: str) -> str:
        """Classifies product name into 'session', 'book', or 'course'."""
        lower = item_name.lower()
        if any(w in lower for w in ["session", "coaching", "consultation", "minute", "1-on-1", "group"]):
            return "session"
        if any(w in lower for w in ["book", "guide", "journal", "workbook", "ebook", "pdf"]):
            return "book"
        return "course"

    def fetch_all_customers(self) -> List[Dict[str, Any]]:
        """Paginates through WooCommerce customers API."""
        logger.info(f"Connecting to WooCommerce Customers API at: {self.wp_url}/wp-json/wc/v3/customers")
        auth = (self.wp_user, self.wp_password)
        headers = {"User-Agent": "DSH-RAG-Sync/2.1"}
        customers = []
        page = 1

        while True:
            if self.max_pages and page > self.max_pages:
                break
            try:
                resp = requests.get(
                    f"{self.wp_url}/wp-json/wc/v3/customers",
                    auth=auth,
                    headers=headers,
                    params={"per_page": 50, "page": page},
                    timeout=12,
                    verify=self.ssl_verify
                )
                if resp.status_code == 400 or resp.status_code == 404:
                    # End of pages
                    break
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                customers.extend(data)
                logger.info(f"  Fetched page {page} ({len(data)} customers, total so far: {len(customers)})")
                page += 1
            except Exception as e:
                logger.error(f"Error fetching customers page {page}: {e}")
                break

        return customers

    def fetch_all_orders(self) -> List[Dict[str, Any]]:
        """Paginates through WooCommerce orders API."""
        logger.info(f"Connecting to WooCommerce Orders API at: {self.wp_url}/wp-json/wc/v3/orders")
        auth = (self.wp_user, self.wp_password)
        headers = {"User-Agent": "DSH-RAG-Sync/2.1"}
        orders = []
        page = 1

        while True:
            if self.max_pages and page > self.max_pages:
                break
            try:
                resp = requests.get(
                    f"{self.wp_url}/wp-json/wc/v3/orders",
                    auth=auth,
                    headers=headers,
                    params={"per_page": 50, "page": page, "status": "any"},
                    timeout=12,
                    verify=self.ssl_verify
                )
                if resp.status_code == 400 or resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                orders.extend(data)
                logger.info(f"  Fetched page {page} ({len(data)} orders, total so far: {len(orders)})")
                page += 1
            except Exception as e:
                logger.error(f"Error fetching orders page {page}: {e}")
                break

        return orders

    def sync(self) -> Dict[str, int]:
        stats = {
            "customers_fetched": 0,
            "users_synced": 0,
            "orders_fetched": 0,
            "purchases_synced": 0,
            "past_records_synced": 0
        }

        # 1. Fetch Customers
        customers = self.fetch_all_customers()
        stats["customers_fetched"] = len(customers)
        logger.info(f"Total customers retrieved from WordPress: {len(customers)}")

        # 2. Fetch Orders
        orders = self.fetch_all_orders()
        stats["orders_fetched"] = len(orders)
        logger.info(f"Total orders retrieved from WordPress: {len(orders)}")

        if self.dry_run:
            logger.info("=== DRY-RUN PREVIEW (No changes made to MySQL) ===")
            for c in customers[:5]:
                name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or c.get('username')
                logger.info(f"  [Customer Preview] ID: {c.get('id')} | Name: {name} | Email: {c.get('email')}")
            for o in orders[:5]:
                items = [li.get("name") for li in o.get("line_items", [])]
                logger.info(f"  [Order Preview] Order #{o.get('id')} | Customer: {o.get('customer_id')} ({o.get('billing', {}).get('email')}) | Items: {items}")
            return stats

        # 3. Synchronize into MySQL
        logger.info(f"Opening connection to MySQL database '{self.mysql_db}' at {self.mysql_host}:{self.mysql_port}...")
        conn = self._get_mysql_conn()

        try:
            with conn.cursor() as cur:
                # Sync Customers into users table
                for c in customers:
                    cid = str(c.get("id"))
                    first_name = c.get("first_name", "").strip()
                    last_name = c.get("last_name", "").strip()
                    full_name = f"{first_name} {last_name}".strip()
                    email = (c.get("email") or "").strip().lower()
                    if not full_name:
                        full_name = c.get("username") or (email.split("@")[0].title() if email else f"Customer #{cid}")

                    if cid:
                        cur.execute(
                            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email)",
                            (cid, full_name, email or None)
                        )
                        stats["users_synced"] += 1

                    # Also register email as an alias record if present so searches by email match directly
                    if email and email != cid:
                        cur.execute(
                            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                            (email, full_name, email)
                        )
                        stats["users_synced"] += 1

                # Sync Orders into purchases & past_records tables
                for o in orders:
                    order_id = o.get("id")
                    cid = str(o.get("customer_id") or "")
                    billing = o.get("billing", {}) or {}
                    email = (billing.get("email") or "").strip().lower()
                    created = (o.get("date_created") or "")[:10]
                    status = o.get("status", "completed")

                    # Primary customer ID to tie purchase to
                    primary_uid = cid if cid and cid != "0" else email
                    if not primary_uid:
                        continue

                    # Ensure user exists in users table (for guest checkouts with only email)
                    first_name = billing.get("first_name", "").strip()
                    last_name = billing.get("last_name", "").strip()
                    name = f"{first_name} {last_name}".strip() or (email.split("@")[0].title() if email else f"Customer #{order_id}")
                    cur.execute(
                        "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                        (primary_uid, name, email or None)
                    )

                    line_items = o.get("line_items", []) or []
                    for item in line_items:
                        item_name = item.get("name", "").strip()
                        if not item_name:
                            continue
                        item_type = self._classify_item(item_name)

                        # Insert purchase (avoid duplicate purchase rows for same user and title)
                        cur.execute(
                            "SELECT id FROM purchases WHERE user_id = %s AND item_title = %s LIMIT 1",
                            (primary_uid, item_name)
                        )
                        if not cur.fetchone():
                            cur.execute(
                                "INSERT INTO purchases (user_id, item_type, item_title) VALUES (%s, %s, %s)",
                                (primary_uid, item_type, item_name)
                            )
                            stats["purchases_synced"] += 1

                        # Insert past order record
                        record_summary = f"Order #{order_id}: Purchased '{item_name}' on {created} (Status: {status})"
                        cur.execute(
                            "SELECT id FROM past_records WHERE user_id = %s AND summary_notes = %s LIMIT 1",
                            (primary_uid, record_summary)
                        )
                        if not cur.fetchone():
                            cur.execute(
                                "INSERT INTO past_records (user_id, interaction_type, summary_notes) VALUES (%s, 'Order', %s)",
                                (primary_uid, record_summary)
                            )
                            stats["past_records_synced"] += 1

            logger.info("=== SYNC COMPLETED SUCCESSFULLY ===")
            logger.info(f"  Customers Fetched:    {stats['customers_fetched']}")
            logger.info(f"  Users Upserted:       {stats['users_synced']}")
            logger.info(f"  Orders Fetched:       {stats['orders_fetched']}")
            logger.info(f"  New Purchases Saved:  {stats['purchases_synced']}")
            logger.info(f"  Past Records Added:   {stats['past_records_synced']}")
        finally:
            conn.close()

        return stats


def main():
    parser = argparse.ArgumentParser(description="Synchronize WordPress WooCommerce customer data into MySQL.")
    parser.add_argument("--dry-run", action="store_true", help="Preview extracted data without writing to MySQL.")
    parser.add_argument("--pages", type=int, default=None, help="Maximum number of pages to fetch (default: all).")
    args = parser.parse_args()

    syncer = WordPressToMySQLSyncer(dry_run=args.dry_run, max_pages=args.pages)
    syncer.sync()


if __name__ == "__main__":
    main()
