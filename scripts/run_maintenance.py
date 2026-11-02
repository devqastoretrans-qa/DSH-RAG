#!/usr/bin/env python3
"""
=============================================================================
Doctor Sarah Hensley AI (DSH-RAG) - Automated Server Maintenance Service
=============================================================================
Performs regular operational hygiene on the AWS EC2 instance:
  1. Disk & Resource Audit: Logs disk utilization before and after maintenance.
  2. Database Optimization: Runs VACUUM, PRAGMA optimize, and integrity checks on SQLite databases.
  3. Log Maintenance: Triggers logrotate and systemd journal vacuuming (7-day cap).
  4. Backup Retention Pruning: Automatically cleans up backup archives older than 14 days.
  5. IST Formatted Maintenance Logs: Records summary to logs/maintenance.log.
=============================================================================
"""

import os
import sys
import shutil
import sqlite3
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Indian Standard Time (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT_DIR / "logs"
BACKUPS_DIR = ROOT_DIR / "backups"
MAINTENANCE_LOG = LOGS_DIR / "maintenance.log"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(MAINTENANCE_LOG), encoding="utf-8")
    ]
)
logger = logging.getLogger("dsh_maintenance")


def get_disk_stats() -> dict:
    """Returns disk usage stats for the root filesystem."""
    total, used, free = shutil.disk_usage("/")
    return {
        "total_gb": round(total / (1024**3), 2),
        "used_gb": round(used / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "percent_used": round((used / total) * 100, 1)
    }


def optimize_sqlite_db(db_path: Path):
    """Checks integrity, updates statistics, and vacuums SQLite database."""
    if not db_path.exists():
        logger.info(f"Database {db_path.name} not found on disk, skipping.")
        return

    orig_size = db_path.stat().st_size
    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        cursor = conn.cursor()

        # 1. Quick integrity check
        cursor.execute("PRAGMA quick_check;")
        check_result = cursor.fetchone()
        status_text = check_result[0] if check_result else "unknown"
        if status_text != "ok":
            logger.warning(f"Integrity check warning for {db_path.name}: {status_text}")
        else:
            logger.info(f"Integrity verified for {db_path.name}: {status_text}")

        # 2. Update query optimizer statistics
        cursor.execute("PRAGMA optimize;")

        # 3. Defragment and reclaim free pages
        cursor.execute("VACUUM;")
        conn.close()

        new_size = db_path.stat().st_size
        saved_kb = (orig_size - new_size) / 1024
        logger.info(
            f"Optimized {db_path.name}: {orig_size / 1024:.1f} KB -> {new_size / 1024:.1f} KB "
            f"({saved_kb:+.1f} KB)"
        )
    except Exception as e:
        logger.error(f"Failed to optimize {db_path.name}: {e}")


def vacuum_systemd_journal():
    """Vacuums systemd journal logs to retain at most 7 days of logs."""
    try:
        cmd = ["journalctl", "--vacuum-time=7d"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            output_line = res.stdout.strip().split("\n")[-1] if res.stdout.strip() else "Cleaned"
            logger.info(f"Systemd journal vacuum: {output_line}")
        else:
            logger.warning(f"Systemd journal vacuum warning: {res.stderr.strip()}")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Could not vacuum systemd journal: {e}")


def trigger_logrotate():
    """Runs logrotate for DSH-RAG logs if configuration exists."""
    logrotate_conf = Path("/etc/logrotate.d/dsh-rag")
    if not logrotate_conf.exists():
        return

    try:
        cmd = ["logrotate", "-f", str(logrotate_conf)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            logger.info("Logrotate executed successfully for /home/ubuntu/DSH-RAG/logs.")
        else:
            logger.warning(f"Logrotate output: {res.stderr.strip() or res.stdout.strip()}")
    except Exception as e:
        logger.warning(f"Could not trigger logrotate: {e}")


def prune_old_backups(retention_days: int = 14) -> int:
    """Removes backup archives older than retention_days."""
    if not BACKUPS_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    pruned = 0
    for item in BACKUPS_DIR.glob("*.gz"):
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            if mtime < cutoff:
                item.unlink()
                pruned += 1
                logger.info(f"Pruned expired backup: {item.name} (age: {(datetime.now() - mtime).days} days)")
        except Exception as e:
            logger.warning(f"Could not prune {item.name}: {e}")

    return pruned


def run_maintenance():
    start_time = datetime.now(IST)
    logger.info("==================================================================")
    logger.info(f"[MAINTENANCE] Starting DSH-RAG Scheduled Maintenance Routine [{start_time.strftime('%Y-%m-%d %H:%M:%S IST')}]")
    logger.info("==================================================================")

    # 1. Initial disk stats
    before_disk = get_disk_stats()
    logger.info(
        f"Initial Disk State: {before_disk['used_gb']} GB used / {before_disk['total_gb']} GB total "
        f"({before_disk['free_gb']} GB free, {before_disk['percent_used']}% utilized)"
    )

    # 2. SQLite Database Optimizations
    logger.info("Running SQLite database vacuum and index optimization...")
    optimize_sqlite_db(ROOT_DIR / "users_data.db")
    optimize_sqlite_db(ROOT_DIR / "ingestion_tracker.db")

    # 3. Log & Journal Cleanup
    logger.info("Running journal and log rotation maintenance...")
    vacuum_systemd_journal()
    trigger_logrotate()

    # 4. Backup Retention Pruning
    logger.info("Checking backup archives retention (14-day policy)...")
    pruned = prune_old_backups(retention_days=14)
    logger.info(f"Pruned {pruned} old backup archives.")

    # 5. Final disk stats
    after_disk = get_disk_stats()
    duration = (datetime.now(IST) - start_time).total_seconds()
    logger.info(
        f"Final Disk State: {after_disk['used_gb']} GB used / {after_disk['total_gb']} GB total "
        f"({after_disk['free_gb']} GB free, {after_disk['percent_used']}% utilized)"
    )
    logger.info(f"[SUCCESS] Maintenance completed in {duration:.2f} seconds.")
    logger.info("==================================================================\n")


if __name__ == "__main__":
    run_maintenance()
