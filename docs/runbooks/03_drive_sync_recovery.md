# Operational Runbook: Google Drive Knowledge Sync Recovery
**Document ID:** `RB-03-DRIVE-SYNC`  
**Classification:** Operational Runbook / Data Ingestion  
**Target Application:** Doctor Sarah Hensley AI RAG (`DSH-RAG`)  
**Target Systems:** Google Drive API v3, `ingestion_tracker.db`, Qdrant Vector DB  
**Target RTO:** < 30 minutes  

---

## 1. Sync Architecture Overview
The DSH-RAG system automatically synchronizes clinical documents, relationship workbooks, and guidance PDFs from Dr. Sarah Hensley's Google Drive:

1. **Google Drive Service Account (`src/drive_service.py`)**: Authenticates via `service_account.json` and polls designated shared folders.
2. **Ingestion Tracker (`src/ingestion_tracker.py` & `ingestion_tracker.db`)**: Computes SHA-256 hashes of each file to prevent duplicate processing.
3. **Multi-Format Extractor (`src/document_loader.py`)**: Extracts text from `.pdf`, `.docx`, and `.txt` files.
4. **Recursive Chunker & Embedder (`src/chunker.py`, `src/embeddings.py`)**: Chunks documents into ~500-token blocks with 50-token overlap and generates 384-dimensional vector embeddings (`all-MiniLM-L6-v2`).
5. **Qdrant Storage (`src/qdrant_service.py`)**: Stores vectors and payload metadata into collection `dsh_knowledge_base`.

---

## 2. Common Failure Symptoms

| Symptom | Probable Cause | Action |
| :--- | :--- | :--- |
| `HttpError 401: Invalid Credentials` | Expired / revoked service account key | Reissue GCP key (Runbook 02) |
| `HttpError 403: The user does not have sufficient permissions` | Service account email removed from Google Drive folder | Re-invite service account email in Google Drive |
| New documents added to Drive not answering in RAG | Sync watcher crashed or tracker hash mismatch | Restart sync worker or force manual ingestion |
| `sqlite3.OperationalError: database is locked` | Concurrent write collision on `ingestion_tracker.db` | Clear WAL locks and restart |
| `qdrant_client.http.exceptions.UnexpectedResponse: 502/503` | Qdrant daemon stopped or out of memory | Restart Qdrant service |

---

## 3. Step-by-Step Recovery Procedures

### 3.1. Verify Drive Service Account Access
Check whether the service account can connect to Google Drive API:

```bash
cd /home/ubuntu/DSH-RAG
source venv/bin/activate

# Test API connectivity and list accessible folders
python3 -c "
from src.drive_service import DriveService
try:
    svc = DriveService()
    files = svc.list_files(limit=5)
    print(f'Google Drive Connected! Found {len(files)} files.')
    for f in files:
        print(f' - {f[\"name\"]} (ID: {f[\"id\"]})')
except Exception as e:
    print('Drive Connection Error:', e)
"
```

* **If Error 403**: The service account email (found inside `service_account.json` under `"client_email"`) must be re-added as **Viewer** or **Editor** on Dr. Sarah's Google Drive folder.
* **If Error 401**: Follow **Runbook 02 (Section 3.4)** to rotate `service_account.json`.

---

### 3.2. Inspect Ingestion Tracker Status
Examine which files were processed and whether any errors occurred:

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('ingestion_tracker.db')
cursor = conn.cursor()
cursor.execute('SELECT file_id, file_name, status, last_synced_at FROM ingestion_files ORDER BY last_synced_at DESC LIMIT 10;')
rows = cursor.fetchall()
print(f'Total tracked files: {len(rows)}')
for r in rows:
    print(r)
conn.close()
"
```

---

### 3.3. Trigger a Manual Re-Sync (Safe / Incremental)
If automatic polling missed an update:

```bash
# Run incremental sync (processes only new or modified files)
python3 src/ingest.py
```

Check the log output for:
* `Found X modified documents in Google Drive.`
* `Extracting and chunking...`
* `Uploaded X points to Qdrant collection 'dsh_knowledge_base'.`

---

### 3.4. Force Full Re-Ingestion (Disaster / Inconsistency Recovery)
If documents were modified on Drive but the tracker incorrectly believes they are unchanged, or if Qdrant points were wiped:

```bash
cd /home/ubuntu/DSH-RAG
source venv/bin/activate

# 1. Reset the local tracker database
python3 -c "
import sqlite3
conn = sqlite3.connect('ingestion_tracker.db')
conn.execute('UPDATE ingestion_files SET status = \"pending\", file_hash = \"\";')
conn.commit()
conn.close()
print('Reset all file hashes to force complete re-ingestion.')
"

# 2. Run full ingestion pass
python3 src/ingest.py --force-all

# 3. Clear the semantic query cache so stale answers are flushed
python3 -c "
from src.semantic_cache import SemanticQueryCache
cache = SemanticQueryCache()
cache.clear_cache()
print('Flushed semantic query cache.')
"
```

---

### 3.5. Verify End-to-End Query Retrieval
Verify that the updated knowledge is actively returned by the RAG engine:

```bash
python3 -c "
from src.rag_service import RAGService
rag = RAGService()
ans = rag.query('What does Dr Sarah teach about anxious-avoidant relationship dynamics?')
print('Retrieval successful!')
print('Answer preview:', ans[:150])
"
```

---

## 4. Background Sync Watcher Health Check
The application runs a background sync worker or scheduled cron job:

```bash
# Check if sync service / daemon is active
ps aux | grep -E "watch_drive_sync|ingest" | grep -v grep

# Check cron schedule
crontab -l | grep ingest

# Standard production crontab entry (polls every 30 minutes):
# */30 * * * * cd /home/ubuntu/DSH-RAG && ./venv/bin/python3 src/ingest.py >> /home/ubuntu/DSH-RAG/logs/sync.log 2>&1
```

---

## 5. Recovery Sign-Off Checklist
- [ ] Google Drive API authenticates with HTTP 200.
- [ ] `ingestion_tracker.db` records match files in Google Drive.
- [ ] Qdrant vector count matches expected total chunk count.
- [ ] Sample test query retrieves freshly synced clinical guidelines.
- [ ] Background sync worker / cron is active.
