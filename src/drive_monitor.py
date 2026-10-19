import os
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from src.drive_service import get_drive_service
from src.ingestion_tracker import get_ingestion_tracker
from src.ingestion import ingest_pdf_document
from src.logger import (
    log_application, log_lifecycle_event, LifecycleEvent, IST,
    log_embedding_audit, log_scan_heartbeat
)

load_dotenv()


class DriveMonitor:
    """
    Background polling service that monitors configured Google Drive folder for new
    or modified PDF documents, triggers the automated ingestion pipeline,
    and prevents duplicate processing.
    """

    def __init__(self, poll_interval_seconds: Optional[int] = None):
        self.poll_interval = poll_interval_seconds or int(os.getenv("DRIVE_POLL_INTERVAL_SECONDS", 60))
        self.drive_service = get_drive_service()
        self.tracker = get_ingestion_tracker()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_scanning = False
        self._last_scan_time: Optional[str] = None
        self._last_scan_result: Dict[str, Any] = {}

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> Dict[str, Any]:
        enabled_in_proc = os.getenv("ENABLE_DRIVE_MONITOR", "false").strip().lower() in ("true", "1", "yes")
        return {
            "running": self.is_running(),
            "enabled_in_current_process": enabled_in_proc,
            "worker_mode": "In-Process Thread" if enabled_in_proc else "Dedicated Worker Container",
            "scanning_now": self._is_scanning,
            "poll_interval_seconds": self.poll_interval,
            "last_scan_time": self._last_scan_time,
            "last_scan_result": self._last_scan_result,
            "drive_status": self.drive_service.get_status_info()
        }

    def start(self):
        """Starts the background polling thread if not already running."""
        if self.is_running():
            log_application("INFO", "DriveMonitor is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="DriveMonitorWorker", daemon=True)
        self._thread.start()
        log_application("INFO", f"DriveMonitor background worker started (interval: {self.poll_interval}s).")

    def stop(self):
        """Stops the background polling thread."""
        if not self.is_running():
            return
        log_application("INFO", "Stopping DriveMonitor worker...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        log_application("INFO", "DriveMonitor worker stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.scan_and_process()
            except Exception as e:
                log_application("ERROR", f"Unhandled error in DriveMonitor scan loop: {e}")

            # Sleep in 1-second chunks to respond quickly to stop signal
            for _ in range(self.poll_interval):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def scan_and_process(self, force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Executes a single scan cycle against the Google Drive folder:
        - Identifies new or modified PDF files
        - Skips unchanged already-processed files (unless force_reprocess=True)
        - Ingests new / modified files through automated pipeline
        """
        self._is_scanning = True
        scan_timestamp = datetime.now(IST).isoformat()
        self._last_scan_time = scan_timestamp

        result = {
            "timestamp": scan_timestamp,
            "files_found": 0,
            "processed": 0,
            "skipped": 0,
            "reprocessed": 0,
            "failed": 0,
            "details": []
        }

        try:
            if not self.drive_service.is_configured():
                result["message"] = "Google Drive service is not configured (missing credentials or folder ID)."
                self._last_scan_result = result
                return result

            files = self.drive_service.list_pdf_files()
            result["files_found"] = len(files)

            for file_info in files:
                drive_id = file_info["id"]
                file_name = file_info["name"]
                modified_time = file_info.get("modifiedTime")
                version = file_info.get("version")

                if force_reprocess:
                    should_process = True
                    reason = "FORCE_REPROCESS"
                    existing_doc_id = None
                else:
                    should_process, reason, existing_doc_id = self.tracker.should_process_drive_file(
                        drive_file_id=drive_id,
                        modified_time=modified_time
                    )

                if not should_process:
                    # Duplicate prevention: file already processed and unchanged
                    log_lifecycle_event(
                        event=LifecycleEvent.DOCUMENT_SKIPPED,
                        document_id=existing_doc_id or "unknown",
                        file_name=file_name,
                        stage="drive_scan",
                        status="skipped",
                        drive_file_id=drive_id,
                        reason=reason
                    )
                    result["skipped"] += 1
                    result["details"].append({
                        "file_name": file_name,
                        "drive_file_id": drive_id,
                        "action": "SKIPPED",
                        "reason": reason
                    })
                    continue

                # Process new or updated file
                action = "REPROCESSED" if reason == "REPROCESS" else "PROCESSED"
                if reason == "REPROCESS":
                    result["reprocessed"] += 1
                    log_lifecycle_event(
                        event=LifecycleEvent.DOCUMENT_REPROCESSED,
                        document_id=existing_doc_id or "unknown",
                        file_name=file_name,
                        stage="drive_scan",
                        status="reprocessing_triggered",
                        drive_file_id=drive_id
                    )
                else:
                    result["processed"] += 1

                try:
                    category = file_info.get("category")
                    folder_name = file_info.get("folder_name", "Unknown")
                    log_application("INFO", f"DriveMonitor: Processing '{file_name}' ({drive_id}) [Folder: {folder_name}, Category: {category}] - Reason: {reason}")

                    t_start = time.time()
                    file_bytes = self.drive_service.download_file(drive_id)
                    ingest_res = ingest_pdf_document(
                        file_source=file_bytes,
                        filename=file_name,
                        category=category,
                        drive_file_id=drive_id,
                        file_version=version,
                        modified_time=modified_time
                    )
                    elapsed = time.time() - t_start
                    is_ready = ingest_res.get("status") == "READY"

                    chunks_cnt = ingest_res.get("chunks_created") or ingest_res.get("chunk_count") or 0
                    vectors_cnt = ingest_res.get("vectors_stored") or ingest_res.get("vector_count") or 0

                    log_embedding_audit(
                        file_name=file_name,
                        folder_name=folder_name,
                        category=category or "clinical",
                        embedded=is_ready,
                        chunks=chunks_cnt,
                        vectors=vectors_cnt,
                        duration_seconds=elapsed,
                        details="Vectorized and upserted into Qdrant"
                    )

                    result["details"].append({
                        "file_name": file_name,
                        "category": category,
                        "folder_name": folder_name,
                        "drive_file_id": drive_id,
                        "action": action,
                        "document_id": ingest_res.get("document_id"),
                        "status": ingest_res.get("status")
                    })
                except Exception as e:
                    result["failed"] += 1
                    result["details"].append({
                        "file_name": file_name,
                        "drive_file_id": drive_id,
                        "action": "FAILED",
                        "error": str(e)
                    })
                    log_application("ERROR", f"DriveMonitor: Failed to ingest '{file_name}' ({drive_id}): {e}")
                    log_embedding_audit(
                        file_name=file_name,
                        folder_name=folder_name if 'folder_name' in locals() else "Unknown",
                        category=category if 'category' in locals() else "unknown",
                        embedded=False,
                        error=str(e)
                    )

        except Exception as scan_err:
            log_application("ERROR", f"Error during Drive scan cycle: {scan_err}")
            result["error"] = str(scan_err)
        finally:
            self._is_scanning = False
            self._last_scan_result = result
            # Record 60-second cycle heartbeat
            log_scan_heartbeat(
                files_found=result["files_found"],
                folders_scanned=["RAG_Clinical-Knowledge", "RAG_Sales"],
                processed=result["processed"],
                skipped=result["skipped"]
            )

        return result


_drive_monitor_instance: Optional[DriveMonitor] = None


def get_drive_monitor() -> DriveMonitor:
    global _drive_monitor_instance
    if _drive_monitor_instance is None:
        _drive_monitor_instance = DriveMonitor()
    return _drive_monitor_instance


def run_worker():
    """Runs the DriveMonitor as a dedicated, standalone background worker process."""
    import signal
    import sys

    # Explicitly ensure monitor is enabled for this dedicated worker process
    os.environ["ENABLE_DRIVE_MONITOR"] = "true"

    monitor = get_drive_monitor()
    if not monitor.drive_service.is_configured():
        log_application("WARNING", "DriveMonitor worker cannot start: Google Drive service is not configured (check GOOGLE_DRIVE_FOLDER_ID and credentials).")
        print("[DriveMonitor Worker] Warning: Google Drive service not configured. Exiting.")
        sys.exit(1)

    print("=" * 70)
    print("DSH-RAG DEDICATED GOOGLE DRIVE BACKGROUND WORKER")
    print(f"Polling Interval: {monitor.poll_interval}s")
    print(f"Log File Location: {EMBEDDING_STATUS_LOG_FILE.resolve() if 'EMBEDDING_STATUS_LOG_FILE' in globals() else 'logs/embedding_status.log'}")
    print("=" * 70)

    def handle_shutdown(signum, frame):
        log_application("INFO", f"DriveMonitor worker received signal {signum}. Stopping worker loop...")
        print(f"\n[DriveMonitor Worker] Received signal {signum}. Shutting down gracefully...")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    monitor.start()

    # Keep the main process alive while the background worker thread runs
    try:
        while monitor.is_running():
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        handle_shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    run_worker()
