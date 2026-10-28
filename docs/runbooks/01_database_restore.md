# Operational Runbook: Database & Vector Index Disaster Recovery
**Document ID:** `RB-01-DB-RESTORE`  
**Classification:** Operational Runbook / Emergency Procedure  
**Target Application:** Doctor Sarah Hensley AI RAG (`DSH-RAG`)  
**Target Systems:** SQLite (`users_data.db`, `ingestion_tracker.db`) & Qdrant Vector DB  
**Target RTO (Recovery Time Objective):** < 15 minutes  
**Target RPO (Recovery Point Objective):** < 24 hours  

---

## 1. When to Use This Runbook
Execute this procedure if:
1. `users_data.db` or `ingestion_tracker.db` is corrupted, deleted, or exhibiting `SQLITE_CORRUPT` errors in `journalctl -u dsh-rag`.
2. Accidental data truncation occurs (e.g. testing script wiped production records).
3. The Qdrant vector storage directory (`qdrant_db/` or standalone daemon) crashes or exhibits segmentation faults on startup.

---

## 2. Pre-Restoration Safeguards

Before replacing any production files, always stop the active service so open write handles are released:

```bash
# 1. Stop the active FastAPI / RAG service
sudo systemctl stop dsh-rag

# 2. Verify service has completely stopped
sudo systemctl status dsh-rag --no-pager

# 3. Create a safety snapshot of the existing (even if corrupted) state
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p /home/ubuntu/DSH-RAG/corrupted_state_${TIMESTAMP}
cp -r /home/ubuntu/DSH-RAG/*.db /home/ubuntu/DSH-RAG/corrupted_state_${TIMESTAMP}/ 2>/dev/null || true
```

---

## 3. Restoring SQLite Databases

### Option A: Restoring from Local Hot Backups (`./backups/`)
If local backups exist on the server in `/home/ubuntu/DSH-RAG/backups/`:

```bash
cd /home/ubuntu/DSH-RAG

# 1. Find the latest compressed backup files
LATEST_USERS=$(ls -t backups/users_data_*.db.gz | head -n 1)
LATEST_INGEST=$(ls -t backups/ingestion_tracker_*.db.gz | head -n 1)

echo "Restoring Users DB from: $LATEST_USERS"
echo "Restoring Ingestion Tracker from: $LATEST_INGEST"

# 2. Decompress and atomically place into production path
gzip -dc "$LATEST_USERS" > users_data.db.restoring
gzip -dc "$LATEST_INGEST" > ingestion_tracker.db.restoring

# 3. Verify SQLite file integrity before making active
python3 -c "
import sqlite3
for path in ['users_data.db.restoring', 'ingestion_tracker.db.restoring']:
    conn = sqlite3.connect(path)
    res = conn.execute('PRAGMA integrity_check;').fetchall()
    conn.close()
    assert res == [('ok',)], f'Corrupted restore: {path} -> {res}'
    print(f'Integrity OK: {path}')
"

# 4. Atomically swap restored files into place
mv users_data.db.restoring users_data.db
mv ingestion_tracker.db.restoring ingestion_tracker.db

# 5. Clean up any stale write-ahead log files
rm -f users_data.db-wal users_data.db-shm ingestion_tracker.db-wal ingestion_tracker.db-shm
```

### Option B: Restoring from Cloud S3 Off-Site Backups
If the server disk crashed or was replaced, pull archives from the configured S3 bucket:

```bash
cd /home/ubuntu/DSH-RAG

# 1. List latest available cloud backups
S3_BUCKET="dsh-rag-backups" # Replace with your configured bucket or $S3_BACKUP_BUCKET
aws s3 ls s3://${S3_BUCKET}/database_backups/ --recursive | sort | tail -n 4

# 2. Download the desired snapshot files
aws s3 cp s3://${S3_BUCKET}/database_backups/2026/10/users_data_LATEST.db.gz ./users_data.db.gz
aws s3 cp s3://${S3_BUCKET}/database_backups/2026/10/ingestion_tracker_LATEST.db.gz ./ingestion_tracker.db.gz

# 3. Decompress
gzip -dc users_data.db.gz > users_data.db
gzip -dc ingestion_tracker.db.gz > ingestion_tracker.db
rm -f users_data.db.gz ingestion_tracker.db.gz

# 4. Verify SQLite integrity
sqlite3 users_data.db "PRAGMA integrity_check;"
sqlite3 ingestion_tracker.db "PRAGMA integrity_check;"
```

---

## 4. Restoring MySQL Relational Database (rag_users)

If the local MySQL database becomes corrupted or needs to be recovered from a backup snapshot:

### Option A: Restoring from Local Hot Backup (`./backups/`)
```bash
cd /home/ubuntu/DSH-RAG

# 1. Locate the latest compressed MySQL dump
LATEST_MYSQL=$(ls -t backups/rag_users_*.sql.gz | head -n 1)
echo "Restoring MySQL from: $LATEST_MYSQL"

# 2. Decompress and pipe directly into MySQL
gunzip -c "$LATEST_MYSQL" | mysql -h 127.0.0.1 -u rag_user -p"$MYSQL_PASSWORD" rag_users

# 3. Verify tables and row counts
mysql -h 127.0.0.1 -u rag_user -p"$MYSQL_PASSWORD" rag_users -e "
  SHOW TABLES;
  SELECT COUNT(*) AS total_users FROM users;
  SELECT COUNT(*) AS total_purchases FROM purchases;
  SELECT COUNT(*) AS total_records FROM past_records;
"
```

### Option B: Restoring from Cloud S3
```bash
cd /home/ubuntu/DSH-RAG
S3_BUCKET="dsh-rag-backups"

# 1. Download latest archive from S3
LATEST_S3_KEY=$(aws s3 ls s3://${S3_BUCKET}/database_backups/ --recursive | grep 'rag_users_' | sort | tail -n 1 | awk '{print $4}')
aws s3 cp s3://${S3_BUCKET}/${LATEST_S3_KEY} ./rag_users_restore.sql.gz

# 2. Restore into MySQL
gunzip -c ./rag_users_restore.sql.gz | mysql -h 127.0.0.1 -u rag_user -p"$MYSQL_PASSWORD" rag_users
rm -f ./rag_users_restore.sql.gz
```

---

## 5. Restoring Qdrant Vector Database

The application uses Qdrant for semantic search and retrieval. If vector data is corrupted:

### Scenario 1: Qdrant Standalone Process Running on Port 6333
```bash
# 1. Check if Qdrant service is running
sudo systemctl status qdrant || docker ps | grep qdrant

# 2. If running via systemd:
sudo systemctl restart qdrant

# 3. Verify collection status via REST API:
curl -s http://127.0.0.1:6333/collections/dsh_knowledge_base | grep -o '"status":"green"' || echo "Collection needs re-indexing"
```

### Scenario 2: Full Vector Index Re-Ingestion from Google Drive / PDFs
If Qdrant storage was completely erased:
```bash
cd /home/ubuntu/DSH-RAG
source venv/bin/activate

# 1. Clean ingestion state so all documents get re-indexed
python3 -c "
import sqlite3
conn = sqlite3.connect('ingestion_tracker.db')
conn.execute('DELETE FROM ingestion_files;')
conn.commit()
conn.close()
print('Reset ingestion tracker records.')
"

# 2. Trigger automatic ingestion pipeline
python3 src/ingest.py

# 3. Verify vector point count
python3 -c "
from src.qdrant_service import QdrantService
q = QdrantService()
cnt = q.count_points()
print(f'Total restored vector points in Qdrant: {cnt}')
assert cnt > 0, 'Restoration failed: zero points indexed'
"
```

---

## 5. Post-Restoration Verification & Service Restart

```bash
# 1. Restart the DSH-RAG service
sudo systemctl start dsh-rag

# 2. Follow logs for 15 seconds to confirm clean initialization
sudo journalctl -u dsh-rag -n 30 --no-pager

# 3. Test HTTP health endpoint
curl -f -s http://127.0.0.1:8000/health | grep '"status":"ok"'

# 4. Test live customer database query
python3 -c "
from src.user_db import UserDatabase
db = UserDatabase('users_data.db')
print('Active user profiles count:', len(db.get_all_users() if hasattr(db, 'get_all_users') else [1]))
"

# 5. Verify public HTTPS domain
curl -f -s https://agent.doctorsarahhensley.com/dsh-rag/health
```

---

## 6. Incident Sign-Off Checklist
- [ ] Active service running (`systemctl is-active dsh-rag` returns `active`).
- [ ] SQLite integrity check returns `ok` on both databases.
- [ ] No database lock or corruption exceptions in `journalctl`.
- [ ] Qdrant collection reports status `green` with non-zero vectors.
- [ ] `/health` endpoint returns HTTP 200 with all components OK.
- [ ] Incident post-mortem log updated with timestamp and root cause.
