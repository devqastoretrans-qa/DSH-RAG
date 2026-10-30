import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# Indian Standard Time (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

class ISTFormatter(logging.Formatter):
    """Logging formatter that formats timestamps in Indian Standard Time (IST)."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S IST")

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

APP_LOG_FILE = LOGS_DIR / "application.log"
INGESTION_LOG_FILE = LOGS_DIR / "ingestion.log"
ERRORS_LOG_FILE = LOGS_DIR / "errors.log"
EMBEDDING_STATUS_LOG_FILE = LOGS_DIR / "embedding_status.log"
CHAT_LOG_FILE = LOGS_DIR / "chat.log"

# Rotation settings: Default 10MB per file, keeping 5 backup files (50MB cap per log file)
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 10 * 1024 * 1024))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

# Common formatters
app_formatter = ISTFormatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S IST"
)
raw_formatter = logging.Formatter("%(message)s")

# 1. Root / App logger configuration (application.log with rotation)
app_logger = logging.getLogger("rag_app")
app_logger.setLevel(logging.INFO)

if not app_logger.handlers:
    app_rot_handler = RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    app_rot_handler.setFormatter(app_formatter)
    app_logger.addHandler(app_rot_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(app_formatter)
    app_logger.addHandler(console_handler)

# 2. Ingestion lifecycle logger (ingestion.log with rotation)
ingestion_logger = logging.getLogger("ingestion_lifecycle")
ingestion_logger.setLevel(logging.INFO)
ingestion_logger.propagate = False

if not ingestion_logger.handlers:
    ingestion_handler = RotatingFileHandler(
        INGESTION_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    ingestion_handler.setFormatter(raw_formatter)
    ingestion_logger.addHandler(ingestion_handler)

# 3. Dedicated error logger (errors.log with rotation)
error_logger = logging.getLogger("document_errors")
error_logger.setLevel(logging.ERROR)
error_logger.propagate = False

if not error_logger.handlers:
    error_handler = RotatingFileHandler(
        ERRORS_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    error_handler.setFormatter(raw_formatter)
    error_logger.addHandler(error_handler)

# 4. Drive sync audit logger (embedding_status.log with rotation)
audit_logger = logging.getLogger("drive_audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False

if not audit_logger.handlers:
    audit_handler = RotatingFileHandler(
        EMBEDDING_STATUS_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    audit_handler.setFormatter(raw_formatter)
    audit_logger.addHandler(audit_handler)

# 5. Dedicated chat interactions logger (chat.log with rotation)
chat_logger = logging.getLogger("chat_interactions")
chat_logger.setLevel(logging.INFO)
chat_logger.propagate = False

if not chat_logger.handlers:
    chat_handler = RotatingFileHandler(
        CHAT_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    chat_handler.setFormatter(raw_formatter)
    chat_logger.addHandler(chat_handler)


class LifecycleEvent:
    DOCUMENT_DETECTED = "DOCUMENT_DETECTED"
    DOWNLOAD_STARTED = "DOWNLOAD_STARTED"
    DOWNLOAD_COMPLETED = "DOWNLOAD_COMPLETED"
    EXTRACTION_STARTED = "EXTRACTION_STARTED"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    CLEANING_COMPLETED = "CLEANING_COMPLETED"
    CHUNKING_STARTED = "CHUNKING_STARTED"
    CHUNKING_COMPLETED = "CHUNKING_COMPLETED"
    EMBEDDING_STARTED = "EMBEDDING_STARTED"
    EMBEDDING_COMPLETED = "EMBEDDING_COMPLETED"
    QDRANT_UPSERT_STARTED = "QDRANT_UPSERT_STARTED"
    QDRANT_UPSERT_COMPLETED = "QDRANT_UPSERT_COMPLETED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    DOCUMENT_READY = "DOCUMENT_READY"
    DOCUMENT_FAILED = "DOCUMENT_FAILED"
    DOCUMENT_SKIPPED = "DOCUMENT_SKIPPED"
    DOCUMENT_REPROCESSED = "DOCUMENT_REPROCESSED"


def log_application(level: str, message: str, **kwargs):
    """Logs generic application messages."""
    extra_str = f" | {kwargs}" if kwargs else ""
    log_func = getattr(app_logger, level.lower(), app_logger.info)
    log_func(f"{message}{extra_str}")


def log_lifecycle_event(
    event: str,
    document_id: str,
    file_name: str,
    stage: str,
    status: str = "success",
    drive_file_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    retry_count: int = 0,
    **extra_metrics
) -> Dict[str, Any]:
    """
    Records a structured lifecycle event into both ingestion.log (human-readable + JSON)
    and errors.log if status is failure, safely managed by RotatingFileHandlers.
    """
    now_ist = datetime.now(IST)
    timestamp_iso = now_ist.isoformat()
    timestamp_readable = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")

    # Structured JSON log record
    log_record = {
        "timestamp": timestamp_iso,
        "timestamp_ist": timestamp_readable,
        "document_id": document_id,
        "drive_file_id": drive_file_id or "local",
        "file_name": file_name,
        "stage": stage,
        "event": event,
        "status": status,
        "duration_ms": duration_ms,
        "retry_count": retry_count,
        "error": error,
        "error_type": error_type,
        **extra_metrics
    }

    details_part = ""
    if extra_metrics:
        details_part = " | " + ", ".join(f"{k}={v}" for k, v in extra_metrics.items())
    elif error:
        details_part = f" | error={error}"
    elif duration_ms:
        details_part = f" | duration={duration_ms}ms"

    level = "ERROR" if status == "failed" else "INFO"
    human_line = f"{timestamp_readable} | {level} | {document_id} | {event} | {file_name}{details_part}"

    # Write safely to rotating ingestion.log
    ingestion_logger.info(human_line)

    # Write structured JSON to application log
    app_logger.info(f"[{event}] {json.dumps(log_record)}")

    # If error / failed, append safely to rotating errors.log
    if status == "failed" or error:
        error_entry = (
            f"============================================================\n"
            f"DOCUMENT_FAILED\n"
            f"timestamp: {timestamp_readable} ({timestamp_iso})\n"
            f"document_id: {document_id}\n"
            f"drive_file_id: {drive_file_id or 'local'}\n"
            f"file: {file_name}\n"
            f"failed_stage: {stage}\n"
            f"error_type: {error_type or 'GeneralException'}\n"
            f"error_message: {error}\n"
            f"retry_count: {retry_count}\n"
            f"============================================================"
        )
        error_logger.error(error_entry)

    return log_record


def get_recent_logs(max_lines: int = 50, log_type: str = "ingestion") -> List[str]:
    """
    Returns recent log lines with IST timestamps from the specified log file.
    """
    if log_type == "embedding_status":
        target_file = EMBEDDING_STATUS_LOG_FILE
    elif log_type == "ingestion":
        target_file = INGESTION_LOG_FILE
    elif log_type == "errors":
        target_file = ERRORS_LOG_FILE
    elif log_type == "chat":
        target_file = CHAT_LOG_FILE
    else:
        target_file = APP_LOG_FILE

    if not target_file.exists():
        return []
    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-max_lines:] if line.strip()]
    except Exception:
        return []


def log_embedding_audit(
    file_name: str,
    folder_name: str,
    category: str,
    embedded: bool,
    chunks: int = 0,
    vectors: int = 0,
    duration_seconds: float = 0.0,
    details: str = "",
    error: Optional[str] = None
):
    """
    Dedicated audit logger tracking file embedding events in IST with duration,
    managed by a RotatingFileHandler to prevent unbounded growth.
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    status_str = "EMBEDDED: YES" if embedded else "EMBEDDED: NO"

    line = (
        f"[{now_ist}] | File: {file_name} | Folder: {folder_name} | Category: {category} | "
        f"Status: {status_str} | Chunks: {chunks} | Vectors: {vectors} | "
        f"Duration: {duration_seconds:.2f}s (Within 60s poll)"
    )
    if error:
        line += f" | Error: {error}"
    elif details:
        line += f" | Details: {details}"

    # Write safely to rotating audit log
    audit_logger.info(line)
    app_logger.info(f"[EMBEDDING_AUDIT] {line}")


def log_scan_heartbeat(
    files_found: int,
    folders_scanned: Optional[List[str]] = None,
    processed: int = 0,
    skipped: int = 0
):
    """
    Heartbeat logger recording Drive 60-second polling cycle status to rotating audit log.
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    folders_str = ", ".join(folders_scanned) if folders_scanned else "RAG_Clinical-Knowledge, RAG_Sales"
    if files_found == 0:
        line = f"[{now_ist}] | Drive Scan (60s cycle) | Monitored: [{folders_str}] | Files Found: 0 | Status: WAITING_FOR_UPLOADS (Next poll in 60s)"
    else:
        line = f"[{now_ist}] | Drive Scan (60s cycle) | Monitored: [{folders_str}] | Files Found: {files_found} | Processed: {processed} | Skipped: {skipped}"

    audit_logger.info(line)


def log_chat_interaction(
    user_id: str,
    conversation_id: str,
    user_query: str,
    assistant_answer: str,
    mode: str = "generic",
    sources: Optional[List[str]] = None,
    duration_seconds: Optional[float] = None
):
    """
    Appends a structured, human-readable record of user queries and bot answers
    to logs/chat.log in Indian Standard Time (IST).
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    sources_str = ", ".join(sources) if sources else "None / Direct / Guardrail"
    dur_str = f" | Latency: {duration_seconds:.2f}s" if duration_seconds is not None else ""

    clean_q = user_query.strip()
    clean_a = assistant_answer.strip()

    entry = (
        f"================================================================================\n"
        f"[{now_ist}] USER: {user_id} | MODE: {mode} | SESSION: {conversation_id}{dur_str}\n"
        f"SOURCES : {sources_str}\n"
        f"--------------------------------------------------------------------------------\n"
        f"QUESTION:\n{clean_q}\n\n"
        f"ANSWER:\n{clean_a}\n"
        f"================================================================================\n"
    )
    chat_logger.info(entry)

