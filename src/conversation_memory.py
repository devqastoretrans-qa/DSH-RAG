"""
High-Performance Conversational Memory & Zero-Latency Entity Stitching Engine.

Features:
1. Configurable Conversation Window (default 5 exchanges = 10 messages).
2. Shared SQLite Store with TTL eviction for multi-worker support on small EC2 boxes.
3. Fast Heuristic Anaphora / Follow-up Query Rewriting (<0.1ms).
4. Topic Entity Stitching for Pronouns and Vague Queries ("can you explain that simply?", "what about the price?").
5. Parent Chunk Reuse on Drill-Downs.
6. Session Reset capability for "New chat".
"""
import os
import time
import re
import uuid
import sqlite3
import threading
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("conversation_memory")

CHAT_HISTORY_TURNS = int(os.getenv("CHAT_HISTORY_TURNS", "5"))
CHAT_HISTORY_TTL_SECONDS = int(os.getenv("CHAT_HISTORY_TTL_SECONDS", "7200"))  # 2 hours idle TTL

FOLLOW_UP_PATTERNS = [
    re.compile(r"^\s*(tell|say|explain|elaborate|clarify|give|show|break\s+down)\s+(me\s+)?(more|further|details?|an?\s+example|simply|more\s+simply|easier)\b", re.I),
    re.compile(r"\b(tell\s+more|more\s+about\s+(it|this|that)|what\s+about\s+(it|this|that|the\s+price|pricing|cost))\b", re.I),
    re.compile(r"^\s*(why\s+so|how\s+so|what\s+else|and\s+then|what\s+next|what\s+should\s+i\s+do)\b", re.I),
    re.compile(r"^\s*(can\s+you\s+)?(explain|elaborate\s+on|simplify|summarize|clarify)\s+(it|this|that|further|more\s+simply|simply)\b", re.I),
    re.compile(r"^\s*(give|show)\s+(me\s+)?(an?\s+)?example\b", re.I),
    re.compile(r"^\s*(how\s+much\s+(is|does)\s+(it|that|this))\b", re.I),
    re.compile(r"^\s*(what\s+does\s+(that|this|it)\s+mean)\b", re.I),
]

PRONOUNS_SHORT_QUERY = re.compile(r"\b(it|this|that|them|these|those|steps?|tool|protocol|price|cost)\b", re.I)


class ConversationSession:
    def __init__(self, conversation_id: str, user_id: str):
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.turns: List[Dict[str, str]] = []  # [{"role": "user"|"assistant", "content": "..."}]
        self.last_topic: Optional[str] = None
        self.last_retrieved_chunks: List[Dict[str, Any]] = []
        self.last_mode: str = "generic"
        self.updated_at: float = time.time()

    def add_turn(
        self,
        user_query: str,
        assistant_answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        mode: str = "generic",
        max_turns: int = CHAT_HISTORY_TURNS
    ) -> None:
        self.turns.append({"role": "user", "content": user_query})
        self.turns.append({"role": "assistant", "content": assistant_answer})
        
        # Keep sliding window to last N turns (user + assistant pairs)
        if len(self.turns) > max_turns * 2:
            self.turns = self.turns[-(max_turns * 2):]

        # Extract/preserve topic entity
        self.last_topic = self._extract_topic_entity(user_query, self.last_topic)
        self.last_retrieved_chunks = retrieved_chunks or []
        self.last_mode = mode
        self.updated_at = time.time()

    def _extract_topic_entity(self, query: str, previous_topic: Optional[str]) -> str:
        clean = query.strip()
        words = clean.split()
        if len(words) >= 3 and not any(p.search(clean) for p in FOLLOW_UP_PATTERNS):
            topic_str = re.sub(
                r"^(what\s+is|what\s+are|how\s+to|how\s+does|can\s+you\s+tell\s+me\s+about|tell\s+me\s+about|explain)\s+",
                "",
                clean,
                flags=re.I
            ).strip().rstrip("?.!")
            if len(topic_str) > 3:
                return topic_str
        return previous_topic or clean


class ConversationMemoryManager:
    """Thread-safe conversation manager with hybrid SQLite persistence and fast in-memory LRU cache."""

    def __init__(self, ttl_seconds: int = CHAT_HISTORY_TTL_SECONDS, max_sessions: int = 500, max_turns: int = CHAT_HISTORY_TURNS):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.max_turns = max_turns
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.RLock()
        
        # SQLite persistence setup
        base_dir = Path(__file__).resolve().parent.parent
        self.db_path = base_dir / "users_data.db"
        self._init_sqlite()

        # MySQL persistence setup
        self.mysql_host = os.getenv("MYSQL_HOST", "").strip()
        self.mysql_port = int(os.getenv("MYSQL_PORT", 3306))
        self.mysql_user = os.getenv("MYSQL_USER", "").strip()
        self.mysql_password = os.getenv("MYSQL_PASSWORD", "").strip()
        self.mysql_db = os.getenv("MYSQL_DATABASE", "rag_users").strip()
        self.has_mysql = False

        if self.mysql_host:
            try:
                import pymysql
                self._init_mysql()
                self.has_mysql = True
            except Exception:
                self.has_mysql = False

    def _get_mysql_conn(self):
        import pymysql
        return pymysql.connect(
            host=self.mysql_host,
            port=self.mysql_port,
            user=self.mysql_user,
            password=self.mysql_password,
            database=self.mysql_db,
            autocommit=True
        )

    def _init_mysql(self) -> None:
        try:
            with self._get_mysql_conn() as conn:
                with conn.cursor() as cur:
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
                            is_orphaned INT NOT NULL DEFAULT 0,
                            owner_status VARCHAR(20) NOT NULL DEFAULT 'verified',
                            INDEX idx_conv_session (session_key, created_at),
                            INDEX idx_conv_user_created (user_id, created_at),
                            INDEX idx_conv_user_session (user_id, conversation_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                    """)
        except Exception:
            pass

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    def _init_sqlite(self) -> None:
        """Ensures conversation history table exists for multi-worker persistence."""
        try:
            with self._get_sqlite_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_key TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        topic TEXT,
                        mode TEXT,
                        created_at REAL NOT NULL,
                        is_orphaned INTEGER NOT NULL DEFAULT 0,
                        owner_status TEXT NOT NULL DEFAULT 'verified'
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_turns (session_key, created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_created ON conversation_turns (user_id, created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_session ON conversation_turns (user_id, conversation_id)")
                conn.commit()
        except Exception:
            pass

    def _session_key(self, user_id: str, conversation_id: Optional[str]) -> str:
        uid = user_id.strip() if user_id and user_id.strip() else "guest"
        # Security hardening (DEF-02): Prevent cross-visitor session history leakage
        if uid == "guest":
            if not conversation_id or conversation_id.strip() in ("", "default_conv"):
                # Standalone ephemeral key - never shared across callers
                return f"guest_ephemeral:{uuid.uuid4().hex}"
            return f"guest:{conversation_id.strip()}"
        cid = conversation_id.strip() if conversation_id and conversation_id.strip() else "default_conv"
        return f"{uid}:{cid}"

    def _get_or_load_session(self, user_id: str, conversation_id: Optional[str]) -> Optional[ConversationSession]:
        """Looks up session in memory, or loads from SQLite on worker restart/handoff."""
        uid = user_id.strip() if user_id and user_id.strip() else "guest"
        if uid == "guest" and (not conversation_id or conversation_id.strip() in ("", "default_conv")):
            # Unauthenticated guest with no explicit session ID has zero prior history
            return None

        key = self._session_key(user_id, conversation_id)
        if key in self._sessions:
            return self._sessions[key]

        # Load from MySQL if active
        if self.has_mysql:
            try:
                now = time.time()
                cutoff = now - self.ttl_seconds
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT role, content, topic, mode, created_at
                            FROM conversation_turns
                            WHERE session_key = %s AND created_at >= %s
                            ORDER BY created_at ASC, id ASC
                            LIMIT %s
                        """, (key, cutoff, self.max_turns * 2))
                        rows = cursor.fetchall()
                if rows:
                    cid = conversation_id.strip() if conversation_id and conversation_id.strip() else "default_conv"
                    session = ConversationSession(conversation_id=cid, user_id=user_id)
                    last_topic = None
                    last_mode = "generic"
                    for role, content, topic, mode, created_at in rows:
                        session.turns.append({"role": role, "content": content})
                        if topic:
                            last_topic = topic
                        if mode:
                            last_mode = mode
                    session.last_topic = last_topic
                    session.last_mode = last_mode
                    session.updated_at = rows[-1][4]
                    self._sessions[key] = session
                    return session
            except Exception:
                pass

        # Load from SQLite if exists and within TTL
        try:
            now = time.time()
            cutoff = now - self.ttl_seconds
            with self._get_sqlite_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT role, content, topic, mode, created_at
                    FROM conversation_turns
                    WHERE session_key = ? AND created_at >= ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                """, (key, cutoff, self.max_turns * 2))
                rows = cursor.fetchall()

            if rows:
                cid = conversation_id.strip() if conversation_id and conversation_id.strip() else "default_conv"
                session = ConversationSession(conversation_id=cid, user_id=user_id)
                last_topic = None
                last_mode = "generic"
                for role, content, topic, mode, created_at in rows:
                    session.turns.append({"role": role, "content": content})
                    if topic:
                        last_topic = topic
                    if mode:
                        last_mode = mode
                session.last_topic = last_topic
                session.last_mode = last_mode
                session.updated_at = rows[-1][4]
                self._sessions[key] = session
                return session
        except Exception:
            pass

        return None

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [k for k, s in self._sessions.items() if now - s.updated_at > self.ttl_seconds]
        for k in expired:
            self._sessions.pop(k, None)

        if len(self._sessions) > self.max_sessions:
            sorted_keys = sorted(self._sessions.keys(), key=lambda k: self._sessions[k].updated_at)
            for k in sorted_keys[: len(self._sessions) - self.max_sessions]:
                self._sessions.pop(k, None)

        # Periodic SQLite TTL purge (prune old turns older than 2 hours)
        try:
            cutoff = now - self.ttl_seconds
            with self._get_sqlite_conn() as conn:
                conn.execute("DELETE FROM conversation_turns WHERE created_at < ?", (cutoff,))
                conn.commit()
        except Exception:
            pass

    def resolve_follow_up(
        self,
        user_id: str,
        conversation_id: Optional[str],
        query: str
    ) -> Tuple[str, bool, Optional[List[Dict[str, Any]]]]:
        """
        Rewrites the latest message into a standalone query using conversation history.
        Returns:
            (rewritten_standalone_query, can_reuse_parent_chunks, cached_parent_chunks)
        """
        clean = query.strip()
        uid = user_id.strip() if user_id and user_id.strip() else "guest"
        if uid == "guest" and (not conversation_id or conversation_id.strip() in ("", "default_conv")):
            return clean, False, None
        with self._lock:
            key = self._session_key(user_id, conversation_id)
            session = self._get_or_load_session(user_id, conversation_id)

            if not session or not session.turns or not session.last_topic:
                return clean, False, None

            words = clean.split()
            is_follow_up = False
            is_direct_elaboration = False

            # Check explicit follow up phrases
            for pat in FOLLOW_UP_PATTERNS:
                if pat.search(clean):
                    is_follow_up = True
                    if any(w in clean.lower() for w in ["tell more", "more about", "elaborate", "details"]):
                        is_direct_elaboration = True
                    break

            # Check short query with pronoun
            if not is_follow_up and len(words) <= 7 and PRONOUNS_SHORT_QUERY.search(clean):
                is_follow_up = True

            if is_follow_up and session.last_topic:
                # Context-aware query rewriting
                clean_lower = clean.lower()
                if any(w in clean_lower for w in ["price", "cost", "how much"]):
                    rewritten_query = f"price and cost of {session.last_topic}"
                elif any(w in clean_lower for w in ["simply", "simple", "easier"]):
                    rewritten_query = f"simple explanation of {session.last_topic} in plain terms"
                elif any(w in clean_lower for w in ["example", "scenario"]):
                    rewritten_query = f"example of {session.last_topic} in relationships"
                else:
                    rewritten_query = f"{clean} regarding {session.last_topic}"

                # Check if we can reuse parent chunks (drill-down optimization)
                if is_direct_elaboration and session.last_retrieved_chunks:
                    has_parent = any(c.get("parent_context") or len(c.get("text", "")) > 100 for c in session.last_retrieved_chunks)
                    if has_parent:
                        return rewritten_query, True, session.last_retrieved_chunks

                return rewritten_query, False, None

        return clean, False, None

    def record_turn(
        self,
        user_id: str,
        conversation_id: Optional[str],
        user_query: str,
        assistant_answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        mode: str = "generic"
    ) -> None:
        """Stores the turn in memory and persists to SQLite, dropping older turns beyond limit."""
        with self._lock:
            self._cleanup_expired()
            uid = user_id.strip() if user_id and user_id.strip() else "guest"
            key = self._session_key(user_id, conversation_id)
            cid = conversation_id.strip() if conversation_id and conversation_id.strip() else key

            if key not in self._sessions:
                self._sessions[key] = ConversationSession(conversation_id=cid, user_id=uid)

            self._sessions[key].add_turn(
                user_query=user_query,
                assistant_answer=assistant_answer,
                retrieved_chunks=retrieved_chunks,
                mode=mode,
                max_turns=self.max_turns
            )

            # Persist to MySQL for zero-lock multi-worker sharing
            if self.has_mysql:
                try:
                    now = time.time()
                    topic = self._sessions[key].last_topic
                    with self._get_mysql_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO conversation_turns (session_key, user_id, conversation_id, role, content, topic, mode, created_at, is_orphaned, owner_status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 'verified')
                            """, (key, user_id, cid, "user", user_query, topic, mode, now))
                            cur.execute("""
                                INSERT INTO conversation_turns (session_key, user_id, conversation_id, role, content, topic, mode, created_at, is_orphaned, owner_status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 'verified')
                            """, (key, user_id, cid, "assistant", assistant_answer, topic, mode, now))
                except Exception:
                    pass

            # Persist to SQLite as local backup
            try:
                now = time.time()
                topic = self._sessions[key].last_topic
                with self._get_sqlite_conn() as conn:
                    conn.execute("""
                        INSERT INTO conversation_turns (session_key, user_id, conversation_id, role, content, topic, mode, created_at, is_orphaned, owner_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'verified')
                    """, (key, user_id, cid, "user", user_query, topic, mode, now))
                    conn.execute("""
                        INSERT INTO conversation_turns (session_key, user_id, conversation_id, role, content, topic, mode, created_at, is_orphaned, owner_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'verified')
                    """, (key, user_id, cid, "assistant", assistant_answer, topic, mode, now))

                    # Prune turns older than the sliding window (max_turns * 2 messages)
                    conn.execute("""
                        DELETE FROM conversation_turns
                        WHERE session_key = ? AND id NOT IN (
                            SELECT id FROM conversation_turns
                            WHERE session_key = ?
                            ORDER BY created_at DESC, id DESC
                            LIMIT ?
                        )
                    """, (key, key, self.max_turns * 2))

                    conn.commit()
            except Exception:
                pass

            # Persist to human-readable logs/chat.log
            try:
                from src.logger import log_chat_interaction
                src_list = []
                if retrieved_chunks:
                    for c in retrieved_chunks:
                        name = c.get("document_name") or c.get("filename") or str(c.get("document", ""))
                        if name and name not in src_list:
                            src_list.append(name)
                log_chat_interaction(
                    user_id=user_id,
                    conversation_id=cid,
                    user_query=user_query,
                    assistant_answer=assistant_answer,
                    mode=mode,
                    sources=src_list
                )
            except Exception:
                pass

    def get_chat_history(
        self,
        user_id: str,
        conversation_id: Optional[str],
        max_turns: int = CHAT_HISTORY_TURNS
    ) -> List[Dict[str, str]]:
        """Returns recent chat turns formatted for LLM completion context."""
        uid = user_id.strip() if user_id and user_id.strip() else "guest"
        if uid == "guest" and (not conversation_id or conversation_id.strip() in ("", "default_conv")):
            return []

        with self._lock:
            session = self._get_or_load_session(user_id, conversation_id)
            if not session or not session.turns:
                return []
            # Return last N turn pairs (e.g. 5 pairs = 10 messages)
            return list(session.turns[-(max_turns * 2):])

    def clear(self, user_id: Optional[str] = None, conversation_id: Optional[str] = None, mode: Optional[str] = None) -> None:
        with self._lock:
            if not user_id and not conversation_id and not mode:
                self._sessions.clear()
                try:
                    with self._get_sqlite_conn() as conn:
                        conn.execute("DELETE FROM conversation_turns")
                        conn.commit()
                except Exception:
                    pass
            elif conversation_id:
                if mode:
                    clean_mode = "sales" if str(mode).lower() == "sales" else "generic"
                    keys_to_remove = [k for k in self._sessions if conversation_id in k and (clean_mode in k or getattr(self._sessions[k], "last_mode", None) == clean_mode)]
                    for k in keys_to_remove:
                        self._sessions.pop(k, None)
                    try:
                        with self._get_sqlite_conn() as conn:
                            conn.execute(
                                "DELETE FROM conversation_turns WHERE (conversation_id = ? OR session_key LIKE ?) AND mode = ?",
                                (conversation_id, f"%:{conversation_id}%", clean_mode)
                            )
                            conn.commit()
                    except Exception:
                        pass
                else:
                    keys_to_remove = [k for k in self._sessions if conversation_id in k or k == conversation_id]
                    for k in keys_to_remove:
                        self._sessions.pop(k, None)
                    try:
                        with self._get_sqlite_conn() as conn:
                            conn.execute(
                                "DELETE FROM conversation_turns WHERE conversation_id = ? OR session_key LIKE ?",
                                (conversation_id, f"%:{conversation_id}%")
                            )
                            conn.commit()
                    except Exception:
                        pass
            elif user_id:
                to_remove = [k for k in self._sessions if k.startswith(f"{user_id}:")]
                for k in to_remove:
                    self._sessions.pop(k, None)
                try:
                    with self._get_sqlite_conn() as conn:
                        if mode:
                            clean_mode = "sales" if str(mode).lower() == "sales" else "generic"
                            conn.execute("DELETE FROM conversation_turns WHERE user_id = ? AND mode = ?", (user_id, clean_mode))
                        else:
                            conn.execute("DELETE FROM conversation_turns WHERE user_id = ?", (user_id,))
                        conn.commit()
                except Exception:
                    pass

    def clear_session(self, session_id: str, user_id: str, mode: Optional[str] = None) -> None:
        """Explicitly resets conversation history for a given session_id owned by user_id in both memory and SQLite."""
        if not user_id or str(user_id).strip().lower() in ("", "guest", "none", "null"):
            return
        self.clear(user_id=user_id, conversation_id=session_id, mode=mode)

    def delete_session(self, user_id: str, conversation_id: str) -> bool:
        """
        Securely deletes a session belonging strictly to user_id.
        Returns True if deleted, False if session not found or owned by another user.
        """
        if not user_id or not conversation_id:
            return False
        
        uid = str(user_id).strip()
        cid = str(conversation_id).strip()
        if uid.lower() in ("", "guest", "none", "null"):
            return False

        found = False

        # 1. Check & Delete in MySQL if active
        if self.has_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM conversation_turns WHERE user_id = %s AND conversation_id = %s LIMIT 1", (uid, cid))
                        if cur.fetchone():
                            found = True
                        cur.execute("DELETE FROM conversation_turns WHERE user_id = %s AND conversation_id = %s", (uid, cid))
            except Exception as e:
                logger.warning(f"[ConversationMemory] MySQL delete session failed: {e}")

        # 2. Check & Delete in SQLite
        try:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM conversation_turns WHERE user_id = ? AND conversation_id = ? LIMIT 1", (uid, cid))
                if cur.fetchone():
                    found = True
                cur.execute("DELETE FROM conversation_turns WHERE user_id = ? AND conversation_id = ?", (uid, cid))
                conn.commit()
        except Exception as e:
            logger.error(f"[ConversationMemory] SQLite delete session error: {e}")

        # 3. Clean memory
        key = self._session_key(uid, cid)
        with self._lock:
            if key in self._sessions:
                found = True
                self._sessions.pop(key, None)

        return found

    def delete_all_sessions(self, user_id: str, mode: Optional[str] = None) -> int:
        """
        Securely deletes all conversation sessions belonging strictly to user_id
        (optionally filtered by bot mode). Never touches other users' records.
        Returns the number of deleted turn rows (or sessions cleared in memory).
        """
        if not user_id:
            return 0
        uid = str(user_id).strip()
        if uid.lower() in ("", "guest", "none", "null"):
            return 0
        clean_mode = str(mode).strip() if mode and str(mode).strip() else None

        deleted = 0
        if self.has_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        if clean_mode:
                            cur.execute(
                                "DELETE FROM conversation_turns WHERE user_id = %s AND mode = %s",
                                (uid, clean_mode)
                            )
                        else:
                            cur.execute(
                                "DELETE FROM conversation_turns WHERE user_id = %s",
                                (uid,)
                            )
                        deleted = max(deleted, cur.rowcount or 0)
            except Exception as e:
                logger.warning(f"[ConversationMemory] MySQL delete_all_sessions failed: {e}")

        try:
            with self._get_sqlite_conn() as conn:
                cur = conn.cursor()
                if clean_mode:
                    cur.execute(
                        "DELETE FROM conversation_turns WHERE user_id = ? AND mode = ?",
                        (uid, clean_mode)
                    )
                else:
                    cur.execute(
                        "DELETE FROM conversation_turns WHERE user_id = ?",
                        (uid,)
                    )
                deleted = max(deleted, cur.rowcount or 0)
                conn.commit()
        except Exception as e:
            logger.error(f"[ConversationMemory] SQLite delete_all_sessions error: {e}")

        prefix = f"{uid}::"
        with self._lock:
            to_remove = []
            for k, history in self._sessions.items():
                if not k.startswith(prefix):
                    continue
                if clean_mode:
                    has_mode = any(t.get("mode") == clean_mode for t in history)
                    if not has_mode and history:
                        continue
                to_remove.append(k)
            for k in to_remove:
                self._sessions.pop(k, None)
                deleted = max(deleted, 1)

        return deleted

    def get_recent_sessions(
        self,
        user_id: str,
        limit: int = 50,
        mode: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns a list of recent conversation sessions strictly for the authenticated user_id.
        Optionally filters by bot mode (e.g., 'generic' or 'sales').
        Excludes orphaned/unowned records and never leaks another user's sessions.
        Includes session_id, user_id, title (derived from first user query), last updated timestamp, and turn count.
        """
        sessions = []
        rows = []
        
        if not user_id or str(user_id).strip().lower() in ("", "guest", "none", "null"):
            return []

        clean_uid = str(user_id).strip()
        clean_mode = str(mode).strip() if mode and str(mode).strip() else None

        # 1. Attempt MySQL query if enabled
        if self.has_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        where_clause = "WHERE user_id = %s AND is_orphaned = 0"
                        params: List[Any] = [clean_uid]
                        if clean_mode:
                            where_clause += " AND mode = %s"
                            params.append(clean_mode)
                        params.append(limit)
                        sql = f"""
                            SELECT 
                                conversation_id,
                                user_id,
                                mode,
                                MIN(created_at) as created_at,
                                MAX(created_at) as updated_at,
                                COUNT(*) as message_count,
                                (SELECT content FROM conversation_turns ct2 WHERE ct2.conversation_id = ct.conversation_id AND ct2.user_id = ct.user_id AND ct2.role = 'user' AND ct2.is_orphaned = 0 ORDER BY ct2.id ASC LIMIT 1) as title
                            FROM conversation_turns ct
                            {where_clause}
                            GROUP BY conversation_id, user_id, mode
                            ORDER BY MIN(created_at) ASC, MIN(id) ASC
                            LIMIT %s
                        """
                        cur.execute(sql, tuple(params))
                        rows = cur.fetchall()
            except Exception as e:
                logger.warning(f"[ConversationMemory] MySQL recent sessions lookup failed, falling back to SQLite: {e}")
                rows = []

        # 2. Fallback to SQLite
        if not rows:
            try:
                with self._get_sqlite_conn() as conn:
                    cur = conn.cursor()
                    where_clause = "WHERE user_id = ? AND is_orphaned = 0"
                    params = [clean_uid]
                    if clean_mode:
                        where_clause += " AND mode = ?"
                        params.append(clean_mode)
                    params.append(limit)
                    sql = f"""
                        SELECT 
                            conversation_id,
                            user_id,
                            mode,
                            MIN(created_at) as created_at,
                            MAX(created_at) as updated_at,
                            COUNT(*) as message_count,
                            (SELECT content FROM conversation_turns ct2 WHERE ct2.conversation_id = ct.conversation_id AND ct2.user_id = ct.user_id AND ct2.role = 'user' AND ct2.is_orphaned = 0 ORDER BY ct2.id ASC LIMIT 1) as title
                        FROM conversation_turns ct
                        {where_clause}
                        GROUP BY conversation_id, user_id, mode
                        ORDER BY MIN(created_at) ASC, MIN(id) ASC
                        LIMIT ?
                    """
                    cur.execute(sql, tuple(params))
                    rows = cur.fetchall()
            except Exception as e:
                logger.error(f"[ConversationMemory] Error querying recent sessions from SQLite: {e}", exc_info=True)
                rows = []

        for idx, row in enumerate(rows, start=1):
            cid, uid, mode, created_at, updated_at, count, raw_title = row
            raw_title_str = (raw_title or "").strip()
            if raw_title_str:
                title = raw_title_str.split("\n")[0].strip()
            else:
                title = "New Conversation"
            if len(title) > 42:
                title = title[:39] + "..."
            sessions.append({
                "session_id": cid,
                "user_id": uid,
                "mode": mode or "generic",
                "chat_number": idx,
                "title": title,
                "message_count": count,
                "created_at": created_at,
                "updated_at": updated_at
            })

        return sessions

    def get_session_turns(
        self,
        user_id: str,
        conversation_id: str,
        limit: int = 50,
        mode: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all persistent message turns for a given (user_id, conversation_id) from MySQL or SQLite.
        Optionally filters by bot mode ('generic' or 'sales').
        Strictly scopes lookup to the authenticated user and ignores orphaned records.
        """
        turns = []
        rows = []

        if not user_id or not conversation_id or str(user_id).strip().lower() in ("", "guest", "none", "null"):
            return []

        clean_uid = str(user_id).strip()
        clean_cid = str(conversation_id).strip()
        clean_mode = str(mode).strip() if mode and str(mode).strip() else None

        if self.has_mysql:
            try:
                with self._get_mysql_conn() as conn:
                    with conn.cursor() as cur:
                        where_clause = "WHERE user_id = %s AND conversation_id = %s AND is_orphaned = 0"
                        params: List[Any] = [clean_uid, clean_cid]
                        if clean_mode:
                            where_clause += " AND mode = %s"
                            params.append(clean_mode)
                        params.append(limit)
                        cur.execute(f"""
                            SELECT role, content, mode, created_at
                            FROM conversation_turns
                            {where_clause}
                            ORDER BY created_at ASC, id ASC
                            LIMIT %s
                        """, tuple(params))
                        rows = cur.fetchall()
            except Exception as e:
                logger.warning(f"[ConversationMemory] MySQL session turns lookup failed, falling back to SQLite: {e}")
                rows = []

        if not rows:
            try:
                with self._get_sqlite_conn() as conn:
                    cur = conn.cursor()
                    where_clause = "WHERE user_id = ? AND conversation_id = ? AND is_orphaned = 0"
                    params = [clean_uid, clean_cid]
                    if clean_mode:
                        where_clause += " AND mode = ?"
                        params.append(clean_mode)
                    params.append(limit)
                    cur.execute(f"""
                        SELECT role, content, mode, created_at
                        FROM conversation_turns
                        {where_clause}
                        ORDER BY created_at ASC, id ASC
                        LIMIT ?
                    """, tuple(params))
                    rows = cur.fetchall()
            except Exception as e:
                logger.error(f"[ConversationMemory] Error loading session turns from SQLite: {e}", exc_info=True)
                rows = []

        for r in rows:
            turns.append({
                "role": r[0],
                "content": r[1],
                "mode": r[2] or "generic",
                "created_at": r[3]
            })

        return turns


# Global Singleton
_conv_memory_instance: Optional[ConversationMemoryManager] = None


def get_conversation_memory() -> ConversationMemoryManager:
    global _conv_memory_instance
    if _conv_memory_instance is None:
        _conv_memory_instance = ConversationMemoryManager()
    return _conv_memory_instance
