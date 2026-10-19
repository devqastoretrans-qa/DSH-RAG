import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from src.logger import IST


class IngestionStatus:
    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    CLEANING = "CLEANING"
    CLEANED = "CLEANED"
    CHUNKING = "CHUNKING"
    CHUNKED = "CHUNKED"
    EMBEDDING = "EMBEDDING"
    EMBEDDED = "EMBEDDED"
    STORING = "STORING"
    STORED = "STORED"
    VERIFYING = "VERIFYING"
    READY = "READY"
    FAILED = "FAILED"


class IngestionTracker:
    """
    Persistent SQLite storage tracking document processing states,
    Drive file versions, retry counts, and ingestion metrics.
    """

    def __init__(self, db_path: Optional[Path] = None):
        base_dir = Path(__file__).resolve().parent.parent
        self.db_path = db_path or (base_dir / "ingestion_tracker.db")
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        drive_file_id TEXT,
                        file_name TEXT NOT NULL,
                        file_version TEXT,
                        modified_time TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        processed_at TEXT,
                        pages_count INTEGER DEFAULT 0,
                        chunk_count INTEGER DEFAULT 0,
                        vector_count INTEGER DEFAULT 0,
                        error TEXT,
                        retry_count INTEGER DEFAULT 0,
                        duration_ms INTEGER DEFAULT 0
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_drive_file_id ON documents(drive_file_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON documents(status)")
                conn.commit()

    def register_document(
        self,
        document_id: str,
        file_name: str,
        drive_file_id: Optional[str] = None,
        file_version: Optional[str] = None,
        modified_time: Optional[str] = None,
        status: str = IngestionStatus.DISCOVERED
    ) -> Dict[str, Any]:
        """Registers a newly discovered document."""
        now_iso = datetime.now(IST).isoformat()
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO documents (
                        document_id, drive_file_id, file_name, file_version, modified_time,
                        status, created_at, updated_at, retry_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    document_id, drive_file_id, file_name, file_version, modified_time,
                    status, now_iso, now_iso
                ))
                conn.commit()
        return self.get_document(document_id)

    def update_status(
        self,
        document_id: str,
        status: str,
        error: Optional[str] = None,
        pages_count: Optional[int] = None,
        chunk_count: Optional[int] = None,
        vector_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
        increment_retry: bool = False
    ) -> Dict[str, Any]:
        """Updates lifecycle stage, metrics, and error state."""
        now_iso = datetime.now(IST).isoformat()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,))
                row = cursor.fetchone()
                if not row:
                    raise KeyError(f"Document ID '{document_id}' not found in tracker.")

                updates = ["status = ?", "updated_at = ?"]
                params = [status, now_iso]

                if status == IngestionStatus.READY:
                    updates.append("processed_at = ?")
                    params.append(now_iso)

                if error is not None:
                    updates.append("error = ?")
                    params.append(error)

                if pages_count is not None:
                    updates.append("pages_count = ?")
                    params.append(pages_count)

                if chunk_count is not None:
                    updates.append("chunk_count = ?")
                    params.append(chunk_count)

                if vector_count is not None:
                    updates.append("vector_count = ?")
                    params.append(vector_count)

                if duration_ms is not None:
                    updates.append("duration_ms = ?")
                    params.append(duration_ms)

                if increment_retry:
                    updates.append("retry_count = retry_count + 1")

                params.append(document_id)
                query = f"UPDATE documents SET {', '.join(updates)} WHERE document_id = ?"
                conn.execute(query, params)
                conn.commit()

        return self.get_document(document_id)

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def get_document_by_drive_id(self, drive_file_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM documents WHERE drive_file_id = ? ORDER BY updated_at DESC LIMIT 1",
                    (drive_file_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def should_process_drive_file(
        self,
        drive_file_id: str,
        modified_time: Optional[str]
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Determines whether a Drive file should be processed:
        Returns (should_process, reason, existing_document_id)
        - NEW: Not yet recorded -> process
        - SKIP: Already READY and modified_time matches -> skip duplicate
        - REPROCESS: Already exists but modified_time changed -> process & replace vectors
        - RETRY: Previously FAILED -> retry
        """
        existing = self.get_document_by_drive_id(drive_file_id)
        if not existing:
            return True, "NEW", None

        existing_status = existing.get("status")
        existing_mod_time = existing.get("modified_time")
        doc_id = existing.get("document_id")

        if existing_status == IngestionStatus.READY:
            if modified_time and existing_mod_time == modified_time:
                return False, "SKIP", doc_id
            else:
                return True, "REPROCESS", doc_id

        if existing_status == IngestionStatus.FAILED:
            return True, "RETRY", doc_id

        # In progress states
        return False, "IN_PROGRESS", doc_id

    def list_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,))
                return [dict(row) for row in cursor.fetchall()]

    def is_document_ready(self, document_id: str) -> bool:
        doc = self.get_document(document_id)
        return bool(doc and doc.get("status") == IngestionStatus.READY)


_tracker_instance: Optional[IngestionTracker] = None


def get_ingestion_tracker() -> IngestionTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = IngestionTracker()
    return _tracker_instance
