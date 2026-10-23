import os
import time
import json
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

# Optional PyMySQL for Direct MySQL integration
try:
    import pymysql
    import pymysql.cursors
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class UserDatabaseManager:
    """
    Manages customer profiles, purchase history (courses, books, sessions), and past consultation records.
    
    Priority Hierarchy:
    1. WordPress WooCommerce REST API (when WORDPRESS_URL & WORDPRESS_APP_PASSWORD are configured)
    2. Direct MySQL Database (when MYSQL_HOST is configured)
    3. Local SQLite Database (automatic zero-config fallback at 'users_data.db')
    """

    def __init__(self):
        # WordPress / PAB Profile API Configuration
        self.wp_url = os.getenv("WORDPRESS_URL", "").strip().rstrip("/")
        self.wp_user = os.getenv("WORDPRESS_USER", "").strip()
        self.wp_password = os.getenv("WORDPRESS_APP_PASSWORD", "").strip()
        self.pab_api_key = os.getenv("PAB_API_KEY") or os.getenv("RAG_API_KEY", "dsh_rag_secret_key_2026")

        # SSL Verification Configuration
        is_production = os.getenv("ENVIRONMENT", "").strip().lower() in ("production", "prod")
        ssl_env = os.getenv("WP_SSL_VERIFY", "true").strip().lower() in ("true", "1", "yes")
        # In production, strictly enforce TLS certificate verification
        self.ssl_verify = True if is_production else ssl_env

        # MySQL Configuration
        self.mysql_host = os.getenv("MYSQL_HOST", "").strip()
        self.mysql_port = int(os.getenv("MYSQL_PORT", 3306))
        self.mysql_user = os.getenv("MYSQL_USER", "").strip()
        self.mysql_password = os.getenv("MYSQL_PASSWORD", "").strip()
        self.mysql_db = os.getenv("MYSQL_DATABASE", "rag_users").strip()

        # Local SQLite Fallback Path
        base_dir = Path(__file__).resolve().parent.parent
        self.sqlite_path = base_dir / "users_data.db"
        self._lock = threading.RLock()

        # Profile cache { user_id: { profile, timestamp } } with 5-minute TTL
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300

        self.backend = "unknown"
        self._init_database()

    def clear_cache(self):
        """Flushes in-memory customer profile cache."""
        with self._lock:
            self._cache.clear()

    def _init_database(self):
        """Initializes tables and verifies connectivity with active backend."""
        # 1. Initialize local SQLite tables unconditionally as local cache & fallback
        self._init_sqlite()

        # 2. Try MySQL if configured
        self.has_mysql = False
        if self.mysql_host and PYMYSQL_AVAILABLE:
            try:
                self._init_mysql()
                self.has_mysql = True
                print(f"[UserDB] Connected to MySQL database '{self.mysql_db}' at {self.mysql_host}:{self.mysql_port}")
            except Exception as e:
                print(f"[UserDB] Failed connecting to MySQL ({e}). Falling back to local SQLite.")

        # 3. Configure WordPress / WooCommerce REST API if credentials exist
        if self.wp_url and self.wp_user and self.wp_password:
            self.backend = "WordPress WooCommerce (REST API)" + (" + MySQL" if self.has_mysql else "")
            print(f"[UserDB] Configured WordPress WooCommerce at {self.wp_url} (User: {self.wp_user}) with {'MySQL' if self.has_mysql else 'in-memory'} caching.")
            return

        # 4. Configure WordPress PAB Inspect Profile API if WORDPRESS_URL is present
        if self.wp_url:
            self.backend = "WordPress PAB Profile API" + (" + MySQL" if self.has_mysql else "")
            print(f"[UserDB] Configured WordPress PAB Profile API at {self.wp_url} with {'MySQL' if self.has_mysql else 'in-memory'} caching.")
            return

        # 5. Standalone MySQL
        if self.has_mysql:
            self.backend = "MySQL"
            return

        # 6. Local SQLite Fallback
        self.backend = "SQLite (Local Fallback)"
        print(f"[UserDB] Initialized local SQLite customer database at '{self.sqlite_path}'.")

    # -------------------------------------------------------------------------
    # WordPress PAB Inspect Profile API Implementation
    # -------------------------------------------------------------------------

    def _get_profile_from_pab_api(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Directly fetches user profile, gamification points, streaks, orders, and meta
        from WordPress PAB Inspect Profile API. Automatically resolves non-numeric usernames/emails to WP User ID.
        URL: {base_url}/wp-json/pab/v1/inspect/profile?user_id={user_id}&fresh=true
        Headers: X-API-Key: {pab_api_key}
        """
        if not self.wp_url:
            return None

        headers = {
            "User-Agent": "DSH-RAG-Client/2.2",
            "X-API-Key": self.pab_api_key,
            "X-API Key": self.pab_api_key
        }

        target_uid = str(identifier).strip()

        # If identifier is non-numeric (e.g. "admin" or email), resolve to WP numeric ID
        if target_uid.lower() in ("admin", "administrator"):
            target_uid = "1"
        elif not target_uid.isdigit():
            try:
                search_url = f"{self.wp_url}/wp-json/wp/v2/users"
                res = requests.get(search_url, params={"search": target_uid}, headers=headers, timeout=5, verify=self.ssl_verify)
                if res.status_code == 200:
                    users_list = res.json()
                    if isinstance(users_list, list) and len(users_list) > 0:
                        resolved_id = users_list[0].get("id")
                        if resolved_id:
                            print(f"[UserDB] Resolved user '{identifier}' -> WP User ID '{resolved_id}'")
                            target_uid = str(resolved_id)
            except Exception as e:
                print(f"[UserDB] WP user lookup warning for '{identifier}': {e}")

        url = f"{self.wp_url}/wp-json/pab/v1/inspect/profile"
        params = {"user_id": target_uid, "fresh": "true"}

        try:
            r = requests.get(url, headers=headers, params=params, timeout=5, verify=self.ssl_verify)
            if r.status_code == 200:
                r.encoding = 'utf-8'
                data = json.loads(r.text)
                profile_raw = data.get("profile") if isinstance(data, dict) else None
                if profile_raw and isinstance(profile_raw, dict):
                    return self._format_pab_profile(profile_raw, identifier)
            else:
                print(f"[UserDB] PAB Profile API returned HTTP status {r.status_code} for user '{identifier}' (target ID '{target_uid}')")
        except Exception as e:
            print(f"[UserDB] Error calling PAB Profile API for user '{identifier}': {e}")

        return None

    def _format_pab_profile(self, p: Dict[str, Any], raw_identifier: str) -> Dict[str, Any]:
        meta = p.get("meta") or {}
        first_name = p.get("first_name") or meta.get("first_name") or p.get("display_name") or str(raw_identifier)
        last_name = meta.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()

        # Orders & Purchases
        orders_raw = p.get("orders")
        courses_purchased = []
        books_purchased = []
        all_purchases = []

        if isinstance(orders_raw, dict):
            products = orders_raw.get("products") or []
            for prod in products:
                title = str(prod)
                all_purchases.append(title)
                if "book" in title.lower() or "guide" in title.lower():
                    books_purchased.append(title)
                else:
                    courses_purchased.append(title)
        elif isinstance(orders_raw, list):
            for item in orders_raw:
                if isinstance(item, dict):
                    title = item.get("title") or item.get("name") or str(item)
                    item_type = item.get("type", "course").lower()
                else:
                    title = str(item)
                    item_type = "course"

                if "book" in item_type or "guide" in title.lower():
                    books_purchased.append(title)
                else:
                    courses_purchased.append(title)
                all_purchases.append(title)

        # Gamification / Program Streaks & Points Log
        program = p.get("program") or {}
        user_streaks = program.get("gamplify_attachmentos_user_streaks") or []
        points_log = program.get("gamplify_attachmentos_points_log") or []

        streaks_formatted = []
        for s in user_streaks:
            if isinstance(s, dict):
                key = str(s.get("streak_key", "")).replace("_", " ").title()
                curr = str(s.get("current_streak", "0"))
                last_act = str(s.get("last_activity_date", ""))
                streaks_formatted.append(f"{key} ({curr}-day streak, last active: {last_act})")

        recent_activities = []
        for log in points_log[:5]:
            if isinstance(log, dict):
                note = log.get("note") or str(log.get("action_key", "")).replace("_", " ").title()
                dt = log.get("daily_date") or log.get("created_at", "")
                recent_activities.append(f"{note} on {dt}")

        has_history = bool(all_purchases or streaks_formatted or recent_activities or p.get("member_since"))

        return {
            "user_id": str(p.get("user_id") or raw_identifier),
            "name": full_name,
            "first_name": first_name,
            "display_name": p.get("display_name") or full_name,
            "email": p.get("email") or (raw_identifier if "@" in raw_identifier else f"{raw_identifier}@example.com"),
            "member_since": p.get("member_since"),
            "locale": p.get("locale"),
            "meta": meta,
            "courses_purchased": courses_purchased,
            "books_purchased": books_purchased,
            "all_purchases": all_purchases,
            "streaks": streaks_formatted,
            "recent_activities": recent_activities,
            "past_records": recent_activities,  # Compatible with existing prompt builder
            "raw_pab_profile": p,
            "has_history": has_history,
            "backend": "PAB Profile API"
        }

    # -------------------------------------------------------------------------
    # WordPress WooCommerce Implementation
    # -------------------------------------------------------------------------

    def _get_profile_from_woocommerce(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Dynamically fetches customer data, completed purchases, and order history
        from WordPress / WooCommerce REST API.
        """
        auth = (self.wp_user, self.wp_password)
        headers = {"User-Agent": "DSH-RAG-Client/2.1"}
        customer = None

        try:
            # 1. Check if identifier is numeric customer ID
            if str(identifier).isdigit():
                r = requests.get(f"{self.wp_url}/wp-json/wc/v3/customers/{identifier}", auth=auth, headers=headers, timeout=8, verify=self.ssl_verify)
                if r.status_code == 200:
                    customer = r.json()

            # 2. Search by email or username in WooCommerce
            if not customer:
                r = requests.get(f"{self.wp_url}/wp-json/wc/v3/customers", auth=auth, headers=headers, params={"search": identifier}, timeout=8, verify=self.ssl_verify)
                if r.status_code == 200 and r.json():
                    customer = r.json()[0]

            # 3. If still not found in WC, check WordPress Users API (/wp-json/wp/v2/users)
            wp_user_obj = None
            if not customer:
                try:
                    if str(identifier).isdigit():
                        r_wp = requests.get(f"{self.wp_url}/wp-json/wp/v2/users/{identifier}?context=edit", auth=auth, headers=headers, timeout=8, verify=self.ssl_verify)
                        if r_wp.status_code == 200:
                            wp_user_obj = r_wp.json()
                    if not wp_user_obj:
                        r_wp = requests.get(f"{self.wp_url}/wp-json/wp/v2/users", auth=auth, headers=headers, params={"search": identifier, "context": "edit"}, timeout=8, verify=self.ssl_verify)
                        if r_wp.status_code == 200 and r_wp.json():
                            wp_user_obj = r_wp.json()[0]
                except Exception as e_wp:
                    pass

            # 4. Fetch Orders (Purchases)
            orders = []
            cid = customer["id"] if customer else (wp_user_obj["id"] if wp_user_obj else None)
            if cid:
                r_orders = requests.get(
                    f"{self.wp_url}/wp-json/wc/v3/orders",
                    auth=auth,
                    headers=headers,
                    params={"customer": cid, "status": "any", "per_page": 20},
                    timeout=8,
                    verify=self.ssl_verify
                )
                if r_orders.status_code == 200:
                    orders = r_orders.json()
            
            if not orders:
                # Search orders directly by identifier (email/name)
                r_orders = requests.get(
                    f"{self.wp_url}/wp-json/wc/v3/orders",
                    auth=auth,
                    headers=headers,
                    params={"search": identifier, "status": "any", "per_page": 20},
                    timeout=8,
                    verify=self.ssl_verify
                )
                if r_orders.status_code == 200:
                    orders = r_orders.json()

            if not customer and not orders and not wp_user_obj:
                # User not found in WooCommerce REST API, let caller check MySQL or fallback
                return None

            # Categorize purchases into courses, books, sessions
            courses = []
            books = []
            sessions = []
            records = []
            if customer:
                name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or customer.get("username", "Customer")
                email = customer.get("email", identifier)
            elif wp_user_obj:
                name = wp_user_obj.get("name") or wp_user_obj.get("slug") or "Admin"
                email = wp_user_obj.get("email", identifier)
            else:
                name = identifier.split('@')[0].title() if '@' in identifier else "Customer"
                email = identifier

            for o in orders:
                created = o.get("date_created", "")[:10]
                status = o.get("status")
                oid = o.get("id")
                for item in o.get("line_items", []):
                    item_name = item.get("name", "")
                    lower = item_name.lower()
                    if "book" in lower or "science of" in lower:
                        books.append(item_name)
                    elif "session" in lower or "coaching" in lower or "minute" in lower:
                        sessions.append(item_name)
                    else:
                        courses.append(item_name)
                    records.append(f"Order #{oid}: Purchased '{item_name}' on {created} (Status: {status})")

            full_name = name

            profile_data = {
                "user_id": str(customer.get("id") if customer else (wp_user_obj.get("id") if wp_user_obj else identifier)),
                "name": full_name,
                "email": email,
                "courses_purchased": list(dict.fromkeys(courses + sessions)),
                "books_purchased": list(dict.fromkeys(books)),
                "all_purchases": list(dict.fromkeys(courses + sessions + books)),
                "purchases_detail": [{"item_type": "product", "item_title": it} for it in (courses + sessions + books)],
                "past_records": records,
                "records_detail": [{"interaction_type": "Order", "summary_notes": r} for r in records],
                "has_history": bool(courses or books or sessions or records),
                "backend": "WordPress WooCommerce (Live REST API)"
            }

            return profile_data

        except Exception as e:
            print(f"[UserDB] WooCommerce request failed: {e}. Falling back to local storage.")
            if getattr(self, "has_mysql", False):
                return self._get_profile_from_mysql(identifier)
            return self._get_profile_from_sqlite(identifier)

    # -------------------------------------------------------------------------
    # SQLite Implementation
    # -------------------------------------------------------------------------

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self):
        with self._lock:
            with self._get_sqlite_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        item_type TEXT NOT NULL,
                        item_title TEXT NOT NULL,
                        purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS past_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        interaction_type TEXT NOT NULL,
                        summary_notes TEXT NOT NULL,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                conn.commit()

            self._seed_sqlite()

    def _seed_sqlite(self):
        with self._get_sqlite_conn() as conn:
            cursor = conn.cursor()

            # Seed John
            cursor.execute("SELECT id FROM users WHERE id = 'john'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (id, name, email) VALUES ('john', 'John', 'john@example.com')")
                cursor.execute("INSERT INTO purchases (user_id, item_type, item_title) VALUES ('john', 'session', '55-minute ADHD session')")
                cursor.execute("INSERT INTO purchases (user_id, item_type, item_title) VALUES ('john', 'book', 'How to Be Calm When Having ADHD')")

            # Seed Sarah
            cursor.execute("SELECT id FROM users WHERE id = 'sarah'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (id, name, email) VALUES ('sarah', 'Sarah', 'sarah@example.com')")
                cursor.execute("INSERT INTO purchases (user_id, item_type, item_title) VALUES ('sarah', 'course', 'Mindfulness and Deep Focus Workshop')")
                cursor.execute("INSERT INTO purchases (user_id, item_type, item_title) VALUES ('sarah', 'book', 'Atomic Habits for Neurodiverse Minds')")
                cursor.execute("INSERT INTO past_records (user_id, interaction_type, summary_notes) VALUES ('sarah', 'Coaching Session', 'Discussed developing an energizing morning routine to reduce sensory overload and afternoon focus slump.')")

            # Seed Guest
            cursor.execute("SELECT id FROM users WHERE id = 'guest'")
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (id, name, email) VALUES ('guest', 'Guest User', 'guest@example.com')")

            conn.commit()

    # -------------------------------------------------------------------------
    # MySQL Implementation
    # -------------------------------------------------------------------------

    def _get_mysql_conn(self):
        return pymysql.connect(
            host=self.mysql_host,
            port=self.mysql_port,
            user=self.mysql_user,
            password=self.mysql_password,
            database=self.mysql_db,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )

    def _init_mysql(self):
        try:
            temp_conn = pymysql.connect(
                host=self.mysql_host,
                port=self.mysql_port,
                user=self.mysql_user,
                password=self.mysql_password,
                autocommit=True
            )
            with temp_conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.mysql_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            temp_conn.close()
        except Exception:
            pass

        with self._get_mysql_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(50) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(100) UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS purchases (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(50) NOT NULL,
                        item_type VARCHAR(50) NOT NULL,
                        item_title VARCHAR(255) NOT NULL,
                        purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS past_records (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(50) NOT NULL,
                        interaction_type VARCHAR(100) NOT NULL,
                        summary_notes TEXT NOT NULL,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)

    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves user background information, verified purchases, and past records.
        Cached in-memory for 5 minutes for sub-millisecond retrieval.
        """
        if not user_id:
            return None

        clean_uid = user_id.strip()

        # Check Cache
        with self._lock:
            cached = self._cache.get(clean_uid)
            if cached and (time.time() - cached["timestamp"]) < self._cache_ttl:
                return cached["profile"]

        profile = None

        # Priority 1: Check Local MySQL Database FIRST (Authoritative synced records in <1ms)
        if getattr(self, "has_mysql", False) or self.backend == "MySQL":
            profile = self._get_profile_from_mysql(clean_uid)

        # Priority 2: Check WordPress PAB Profile API if not found
        if not profile and (self.backend == "WordPress PAB Profile API" or self.wp_url):
            profile = self._get_profile_from_pab_api(clean_uid)

        # Priority 3: Check live WordPress WooCommerce if not found
        if not profile and (self.backend.startswith("WordPress WooCommerce") or self.wp_url):
            profile = self._get_profile_from_woocommerce(clean_uid)

        # Priority 4: Check local SQLite fallback if not found
        if not profile:
            profile = self._get_profile_from_sqlite(clean_uid)

        if not profile:
            # Universal graceful profile for any email/user ID (prevents 404 on network timeout or new guests)
            clean_name = clean_uid.split('@')[0].replace('.', ' ').replace('_', ' ').title() if '@' in clean_uid else str(clean_uid).capitalize()
            profile = {
                "user_id": str(clean_uid),
                "name": clean_name,
                "email": clean_uid if "@" in clean_uid else f"{clean_uid}@example.com",
                "courses_purchased": [],
                "books_purchased": [],
                "all_purchases": [],
                "purchases_detail": [],
                "past_records": [],
                "records_detail": [],
                "has_history": False,
                "backend": "Graceful Fallback"
            }

        if profile:
            with self._lock:
                self._cache[clean_uid] = {"profile": profile, "timestamp": time.time()}

        return profile

    def _get_profile_from_mysql(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._get_mysql_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users WHERE id = %s OR email = %s LIMIT 1", (user_id, user_id))
                    user = cur.fetchone()
                    if not user:
                        return None
                    actual_uid = user.get("id")
                    cur.execute("SELECT item_type, item_title, purchased_at FROM purchases WHERE user_id = %s ORDER BY purchased_at ASC", (actual_uid,))
                    purchases = cur.fetchall()
                    cur.execute("SELECT interaction_type, summary_notes, recorded_at FROM past_records WHERE user_id = %s ORDER BY recorded_at DESC", (actual_uid,))
                    records = cur.fetchall()
                    return self._format_profile(user, purchases, records)
        except Exception as e:
            print(f"[UserDB] MySQL error: {e}")
            return self._get_profile_from_sqlite(user_id)

    def _get_profile_from_sqlite(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE id = ? OR email = ? LIMIT 1", (user_id, user_id))
                user_row = cur.fetchone()
                if not user_row:
                    return None
                user = dict(user_row)
                actual_uid = user.get("id")

                cur.execute("SELECT item_type, item_title, purchased_at FROM purchases WHERE user_id = ? ORDER BY purchased_at ASC", (actual_uid,))
                purchases = [dict(r) for r in cur.fetchall()]

                cur.execute("SELECT interaction_type, summary_notes, recorded_at FROM past_records WHERE user_id = ? ORDER BY recorded_at DESC", (actual_uid,))
                records = [dict(r) for r in cur.fetchall()]

        return self._format_profile(user, purchases, records)

    def _format_profile(self, user: Dict[str, Any], purchases: List[Dict[str, Any]], records: List[Dict[str, Any]]) -> Dict[str, Any]:
        def _clean_val(v):
            if hasattr(v, "isoformat"):
                return v.isoformat()
            if isinstance(v, (bytes, bytearray)):
                return v.decode("utf-8", errors="replace")
            return v

        clean_user = {k: _clean_val(v) for k, v in user.items()} if isinstance(user, dict) else {}
        clean_purchases = [{k: _clean_val(v) for k, v in p.items()} for p in purchases] if purchases else []
        clean_records = [{k: _clean_val(v) for k, v in r.items()} for r in records] if records else []

        courses = [p["item_title"] for p in clean_purchases if p.get("item_type") in ("course", "session", "consultation")]
        books = [p["item_title"] for p in clean_purchases if p.get("item_type") == "book"]
        all_items = [p["item_title"] for p in clean_purchases if p.get("item_title")]
        past_notes = [f"{r.get('interaction_type', 'Note')}: {r.get('summary_notes', '')}" for r in clean_records]

        full_name = clean_user.get("name") or ""
        first_name = full_name.split()[0] if full_name else (clean_user.get("id") or "Customer")

        return {
            "user_id": clean_user.get("id"),
            "name": clean_user.get("name"),
            "first_name": first_name,
            "display_name": clean_user.get("name"),
            "email": clean_user.get("email"),
            "attachment_style": clean_user.get("attachment_style") or "Relationship Student",
            "courses_purchased": courses,
            "books_purchased": books,
            "all_purchases": all_items,
            "purchases_detail": clean_purchases,
            "past_records": past_notes,
            "records_detail": clean_records,
            "has_history": bool(clean_purchases or clean_records),
            "backend": self.backend
        }

    def ingest_woocommerce_order_webhook(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receives raw WooCommerce order webhook payloads (e.g. action: woocommerce_order_status_completed
        or topic: order.created / order.updated), categorizes line items, updates local storage,
        and primes the in-memory cache instantly for sub-millisecond lookups.
        """
        if not order_data or not isinstance(order_data, dict):
            raise ValueError("Invalid order data payload")

        order_id = order_data.get("id")
        created = order_data.get("date_created", "")[:10]
        status = order_data.get("status", "completed")
        customer_id = str(order_data.get("customer_id") or "")
        billing = order_data.get("billing", {}) or {}

        email = (billing.get("email") or order_data.get("email") or "").strip().lower()
        first_name = billing.get("first_name") or order_data.get("first_name", "")
        last_name = billing.get("last_name") or order_data.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or email.split("@")[0].title() or "Customer"

        user_id = customer_id if customer_id and customer_id != "0" else (email or f"order_user_{order_id}")

        courses = []
        books = []
        sessions = []
        records = []

        line_items = order_data.get("line_items", []) or []
        for item in line_items:
            item_name = item.get("name", "")
            lower = item_name.lower()
            if "book" in lower or "science of" in lower:
                books.append(item_name)
            elif "session" in lower or "coaching" in lower or "minute" in lower:
                sessions.append(item_name)
            else:
                courses.append(item_name)
            records.append(f"Order #{order_id}: Purchased '{item_name}' on {created} (Status: {status})")

        # Update MySQL storage if available
        if getattr(self, "has_mysql", False):
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                            (user_id, name, email or None)
                        )
                        if email and email != user_id:
                            cur.execute(
                                "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                                (email, name, email)
                            )
                        for c in (courses + sessions):
                            cur.execute("SELECT id FROM purchases WHERE user_id = %s AND item_title = %s LIMIT 1", (user_id, c))
                            if not cur.fetchone():
                                cur.execute("INSERT INTO purchases (user_id, item_type, item_title) VALUES (%s, 'course', %s)", (user_id, c))
                        for b in books:
                            cur.execute("SELECT id FROM purchases WHERE user_id = %s AND item_title = %s LIMIT 1", (user_id, b))
                            if not cur.fetchone():
                                cur.execute("INSERT INTO purchases (user_id, item_type, item_title) VALUES (%s, 'book', %s)", (user_id, b))
                        for r in records:
                            cur.execute("INSERT INTO past_records (user_id, interaction_type, summary_notes) VALUES (%s, 'Order', %s)", (user_id, r))
            except Exception as e_mysql:
                print(f"[UserDB Webhook] MySQL order write error: {e_mysql}")

        # Update local SQLite storage
        with self._lock:
            with self._get_sqlite_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO users (id, name, email) VALUES (?, ?, ?)",
                    (user_id, name, email or f"{user_id}@example.com")
                )
                for c in (courses + sessions):
                    conn.execute(
                        "INSERT INTO purchases (user_id, item_type, item_title) VALUES (?, 'course', ?)",
                        (user_id, c)
                    )
                for b in books:
                    conn.execute(
                        "INSERT INTO purchases (user_id, item_type, item_title) VALUES (?, 'book', ?)",
                        (user_id, b)
                    )
                for r in records:
                    conn.execute(
                        "INSERT INTO past_records (user_id, interaction_type, summary_notes) VALUES (?, 'Order', ?)",
                        (user_id, r)
                    )

        # Build full profile
        profile = {
            "user_id": user_id,
            "name": name,
            "first_name": first_name or name.split()[0],
            "display_name": name,
            "email": email,
            "attachment_style": "Relationship Student",
            "courses_purchased": list(dict.fromkeys(courses + sessions)),
            "books_purchased": list(dict.fromkeys(books)),
            "all_purchases": list(dict.fromkeys(courses + sessions + books)),
            "purchases_detail": [{"item_type": "product", "item_title": it} for it in (courses + sessions + books)],
            "past_records": records,
            "records_detail": [{"interaction_type": "Order", "summary_notes": r} for r in records],
            "has_history": bool(courses or books or sessions or records),
            "backend": "WooCommerce Webhook (Instant Cache)"
        }

        # Prime in-memory cache for all lookup keys
        with self._lock:
            cache_entry = {"profile": profile, "timestamp": time.time()}
            self._cache[user_id] = cache_entry
            if email:
                self._cache[email] = cache_entry
            if customer_id and customer_id != "0":
                self._cache[customer_id] = cache_entry

        print(f"[UserDB Webhook] Synced customer {name} ({email or user_id}) - {len(courses + sessions + books)} item(s) cached.")
        return profile

    def ingest_woocommerce_customer_webhook(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receives real-time push events from WooCommerce for 'customer.created' or 'customer.updated'.
        Instantly saves the new user's name and email into MySQL and SQLite, and primes the in-memory cache.
        """
        if not customer_data or not isinstance(customer_data, dict):
            raise ValueError("Invalid customer data payload")

        cid = str(customer_data.get("id") or "")
        first_name = (customer_data.get("first_name") or "").strip()
        last_name = (customer_data.get("last_name") or "").strip()
        username = (customer_data.get("username") or "").strip()
        email = (customer_data.get("email") or "").strip().lower()

        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = username or (email.split("@")[0].title() if email else f"Customer #{cid}")

        user_id = cid if cid and cid != "0" else (email or "guest")

        # 1. Update MySQL
        if getattr(self, "has_mysql", False):
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email)",
                            (user_id, full_name, email or None)
                        )
                        if email and email != user_id:
                            cur.execute(
                                "INSERT INTO users (id, name, email) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE name=VALUES(name)",
                                (email, full_name, email)
                            )
            except Exception as e_mysql:
                print(f"[UserDB Webhook] MySQL customer write error: {e_mysql}")

        # 2. Update local SQLite
        with self._lock:
            with self._get_sqlite_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO users (id, name, email) VALUES (?, ?, ?)",
                    (user_id, full_name, email or f"{user_id}@example.com")
                )
                if email and email != user_id:
                    conn.execute(
                        "INSERT OR REPLACE INTO users (id, name, email) VALUES (?, ?, ?)",
                        (email, full_name, email)
                    )

        profile = {
            "user_id": user_id,
            "name": full_name,
            "first_name": first_name or full_name.split()[0],
            "display_name": full_name,
            "email": email,
            "attachment_style": "Relationship Student",
            "courses_purchased": [],
            "books_purchased": [],
            "all_purchases": [],
            "purchases_detail": [],
            "past_records": [],
            "records_detail": [],
            "has_history": False,
            "backend": "WooCommerce Webhook (Instant Customer Sync)"
        }

        # Prime in-memory cache
        with self._lock:
            cache_entry = {"profile": profile, "timestamp": time.time()}
            self._cache[user_id] = cache_entry
            if email:
                self._cache[email] = cache_entry

        print(f"[UserDB Webhook] Synced new customer {full_name} ({email or user_id}) into MySQL.")
        return profile

    def list_users(self) -> List[Dict[str, Any]]:
        """Returns summary list of registered users for dashboard selection."""
        users_list = []
        if self.backend == "WordPress WooCommerce (REST API)":
            try:
                auth = (self.wp_user, self.wp_password)
                r = requests.get(f"{self.wp_url}/wp-json/wc/v3/customers", auth=auth, headers={"User-Agent": "DSH-RAG-Client/2.1"}, params={"per_page": 5}, timeout=6, verify=self.ssl_verify)
                if r.status_code == 200:
                    for c in r.json():
                        p = self.get_user_profile(str(c.get("id")))
                        if p:
                            users_list.append(p)
            except Exception:
                pass

        # Also include MySQL users
        if getattr(self, "has_mysql", False):
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM users ORDER BY name ASC")
                        for r in cur.fetchall():
                            p = self._get_profile_from_mysql(r["id"])
                            if p and not any(u["user_id"] == p["user_id"] for u in users_list):
                                users_list.append(p)
            except Exception:
                pass

        # Also include local simulated personas
        with self._lock:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users ORDER BY name ASC")
                for r in cur.fetchall():
                    p = self._get_profile_from_sqlite(r["id"])
                    if p and not any(u["user_id"] == p["user_id"] for u in users_list):
                        users_list.append(p)

        return users_list

    def get_status(self) -> Dict[str, Any]:
        """Returns database backend status and configuration info."""
        return {
            "backend": self.backend,
            "wordpress_url": self.wp_url if self.wp_url else None,
            "mysql_host": self.mysql_host if self.mysql_host else None,
            "sqlite_path": str(self.sqlite_path),
            "users_count": len(self.list_users())
        }


# Singleton instance
_user_db_instance: Optional[UserDatabaseManager] = None


def get_user_db() -> UserDatabaseManager:
    global _user_db_instance
    if _user_db_instance is None:
        _user_db_instance = UserDatabaseManager()
    return _user_db_instance
