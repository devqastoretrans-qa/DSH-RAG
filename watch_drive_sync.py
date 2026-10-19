import time
from pathlib import Path
from src.drive_monitor import get_drive_monitor
from src.logger import EMBEDDING_STATUS_LOG_FILE

def watch_live():
    print("=" * 70)
    print("DSH-RAG 60-SECOND DRIVE SYNC & EMBEDDING LIVE WATCHER")
    print("=" * 70)
    print(f"Log File Location: {EMBEDDING_STATUS_LOG_FILE.resolve()}")
    print("Polling Google Drive folders: 'RAG_Clinical-Knowledge' & 'RAG_Sales'")
    print("Press CTRL+C anytime to stop.\n")

    monitor = get_drive_monitor()
    
    # Run continuous 60-second scanning loop
    while True:
        try:
            print(f"\n--- Checking Google Drive at {time.strftime('%Y-%m-%d %H:%M:%S')} IST ---")
            res = monitor.scan_and_process()
            files_found = res.get("files_found", 0)
            processed = res.get("processed", 0)
            skipped = res.get("skipped", 0)
            
            print(f"Result: {files_found} files found | {processed} embedded | {skipped} skipped")
            if res.get("details"):
                for d in res["details"]:
                    action = d.get("action")
                    name = d.get("file_name")
                    cat = d.get("category")
                    print(f" -> [{action}] {name} (Category: {cat})")

            # Show last line from log file
            if EMBEDDING_STATUS_LOG_FILE.exists():
                with open(EMBEDDING_STATUS_LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        print(f"Latest Log Entry:\n  {lines[-1].strip()}")

            print("\nWaiting 60 seconds for next cycle...")
            for remaining in range(60, 0, -5):
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nWatcher stopped by user.")
            break
        except Exception as e:
            print(f"Error during scan: {e}")
            time.sleep(10)

if __name__ == "__main__":
    watch_live()
