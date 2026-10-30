import sys
import time
import urllib.request
import ssl
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
api_key = os.getenv('RAG_API_KEY', '').strip()
ctx = ssl.create_default_context()
IST = timezone(timedelta(hours=5, minutes=30))

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT_DIR / "logs" / "chat.log"
MAX_CHATS_TO_KEEP = 20

def fetch_latest_turns_from_production(limit=60):
    url = f"https://agent.doctorsarahhensley.com/api/database/table/conversation_turns?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": api_key, "User-Agent": "ChatLogSyncer/1.0"}
    )
    with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("rows", [])

def format_entry(user_row, assistant_row):
    ts = user_row.get("created_at")
    try:
        now_ist = datetime.fromtimestamp(float(ts), tz=IST).strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        now_ist = str(ts)
        
    uid = user_row.get("user_id")
    cid = user_row.get("conversation_id")
    mode = user_row.get("mode") or assistant_row.get("mode") or "generic"
    q_text = str(user_row.get("content", "")).strip()
    a_text = str(assistant_row.get("content", "")).strip()
    
    return (
        f"================================================================================\n"
        f"[{now_ist}] USER: {uid} | MODE: {mode} | SESSION: {cid}\n"
        f"--------------------------------------------------------------------------------\n"
        f"QUESTION:\n{q_text}\n\n"
        f"ANSWER:\n{a_text}\n"
        f"================================================================================\n\n"
    )

def sync_chat_log(poll_interval=10, continuous=False, max_chats=MAX_CHATS_TO_KEEP):
    print("=" * 70)
    print(f"  Doctor Sarah Hensley AI - Live Rolling Chat Log Syncer (Latest {max_chats})")
    print(f"  Target: https://agent.doctorsarahhensley.com -> logs/chat.log")
    print("=" * 70, flush=True)

    last_latest_ts = None

    while True:
        try:
            # Fetch latest turns from production MySQL (fetch enough to pair 25-30 chats)
            rows = fetch_latest_turns_from_production(limit=max(max_chats * 3, 60))
            rows_sorted = list(reversed(rows))
            
            # Pair user -> assistant
            pairs = []
            curr_user = None
            for r in rows_sorted:
                role = r.get("role")
                if role == "user":
                    curr_user = r
                elif role == "assistant" and curr_user:
                    pairs.append((curr_user, r))
                    curr_user = None

            # Keep strictly the latest MAX_CHATS pairs
            trimmed_pairs = pairs[-max_chats:]
            
            if trimmed_pairs:
                current_latest_ts = trimmed_pairs[-1][0].get("created_at")
                
                # Update file if new chat arrived or first run
                if current_latest_ts != last_latest_ts or not LOG_FILE.exists():
                    last_latest_ts = current_latest_ts
                    
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.write("################################################################################\n")
                        f.write(f"# Doctor Sarah Hensley AI RAG - Live Chat Log (Rolling Latest {len(trimmed_pairs)} Chats)   #\n")
                        f.write(f"# Auto-trimmed: Older chats pruned automatically | Updated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')} #\n")
                        f.write("################################################################################\n\n")
                        
                        for u_row, a_row in trimmed_pairs:
                            f.write(format_entry(u_row, a_row))
                            
                    print(f"[{datetime.now(IST).strftime('%H:%M:%S IST')}] logs/chat.log updated: Displaying latest {len(trimmed_pairs)} chats (older pruned).", flush=True)
                else:
                    if not continuous:
                        print(f"[{datetime.now(IST).strftime('%H:%M:%S IST')}] logs/chat.log is already displaying the latest {len(trimmed_pairs)} chats.", flush=True)

        except Exception as e:
            print(f"[{datetime.now(IST).strftime('%H:%M:%S IST')}] Sync warning: {e}", flush=True)

        if not continuous:
            break
            
        time.sleep(poll_interval)

if __name__ == "__main__":
    is_loop = "--watch" in sys.argv or "-w" in sys.argv
    sync_chat_log(poll_interval=10, continuous=is_loop, max_chats=MAX_CHATS_TO_KEEP)
