# 📖 DSH-RAG Production Operations Runbook

> **Target Service:** Doctor Sarah Hensley AI RAG & Clinical Assistant  
> **Production URL:** `https://agent.doctorsarahhensley.com`  
> **Production Host:** AWS EC2 `18.118.138.91` (Ubuntu 24.04 LTS)  
> **Process Supervisor:** `systemd` (`dsh-rag.service`)  
> **Reverse Proxy:** Nginx + Let's Encrypt SSL  
> **Last Updated:** November 2026  
> **Version:** 2.2.0 (Hardened & Prompt-Optimized)

---

## 📑 Table of Contents
1. [System Architecture & Port Inventory](#1-system-architecture--port-inventory)
2. [Service Management & Operations](#2-service-management--operations)
3. [Live Logging & Monitoring](#3-live-logging--monitoring)
4. [API Endpoints & Authentication Catalog](#4-api-endpoints--authentication-catalog)
5. [Token Optimization & Guardrail Architecture](#5-token-optimization--guardrail-architecture)
6. [Scheduled Cron Tasks & Maintenance](#6-scheduled-cron-tasks--maintenance)
7. [Knowledge Base & Google Drive Ingestion](#7-knowledge-base--google-drive-ingestion)
8. [Incident Response & Disaster Recovery](#8-incident-response--disaster-recovery)

---

## 1. System Architecture & Port Inventory

All backend services are strictly bound to `127.0.0.1` (loopback only) and reverse-proxied through Nginx with HSTS, TLS 1.3, and strict security headers.

| Service | Internal Port / Binding | Process / Container | Purpose |
| :--- | :--- | :--- | :--- |
| **Nginx Web Server** | `0.0.0.0:80`, `0.0.0.0:443` | `nginx` | TLS termination, rate-limiting, and static UI assets |
| **FastAPI Backend** | `127.0.0.1:8000` | `uvicorn` (`dsh-rag.service`) | RAG orchestration, SSE streaming, and chat endpoints |
| **Qdrant Vector DB** | `127.0.0.1:6333` | Native Qdrant daemon | 384-dimensional dense vector search (`documents`) |
| **MySQL 8.4 Server** | `127.0.0.1:3306` | `mysqld` | Relational CRM customer profiles & conversation history |
| **Local SQLite Cache** | `/home/ubuntu/DSH-RAG/*.db` | Embedded | Fast local cache (`users_data.db`, `ingestion_tracker.db`) |

---

## 2. Service Management & Operations

The application runs as a systemd service under the `ubuntu` user with automatic restart on failure.

### Common Service Commands

```bash
# Check service status
sudo systemctl status dsh-rag.service

# Restart service (e.g. after code pull or configuration changes)
sudo systemctl restart dsh-rag.service

# Stop service
sudo systemctl stop dsh-rag.service

# Start service
sudo systemctl start dsh-rag.service

# Check health endpoint directly on host
curl -s http://127.0.0.1:8000/health | jq
```

### Deploying Code Updates to Production

```bash
cd /home/ubuntu/DSH-RAG
git pull origin main
sudo systemctl restart dsh-rag.service
sudo systemctl status dsh-rag.service --no-pager
```

---

## 3. Live Logging & Monitoring

All logs are timestamped in **Indian Standard Time (IST, UTC+05:30)** and automatically rotated by `/etc/logrotate.d/dsh-rag` when they reach 10MB.

### Key Log Files (`/home/ubuntu/DSH-RAG/logs/`)

| Log File | Contents | Typical Inspection Command |
| :--- | :--- | :--- |
| `chat.log` | Complete chat dialogues, user IDs, queries, and bot answers | `tail -f /home/ubuntu/DSH-RAG/logs/chat.log` |
| `application.log` | FastAPI startup, ML pre-warming, and pipeline timing | `tail -f /home/ubuntu/DSH-RAG/logs/application.log` |
| `ingestion.log` | Google Drive file downloads, chunking, and Qdrant upserts | `tail -f /home/ubuntu/DSH-RAG/logs/ingestion.log` |
| `maintenance.log`| Weekly SQLite vacuuming, journal cleanup, and disk stats | `tail -n 50 /home/ubuntu/DSH-RAG/logs/maintenance.log` |
| `backup.log` | Nightly database snapshots and compression ratios | `tail -n 50 /home/ubuntu/DSH-RAG/logs/backup.log` |
| `systemd` | Uvicorn stdout/stderr stream | `journalctl -u dsh-rag.service -f` |

---

## 4. API Endpoints & Authentication Catalog

### Authentication Scheme
1. **Administrative Access:** Pass `X-API-Key: <RAG_API_KEY>` or `Authorization: Bearer <RAG_API_KEY>`.
2. **Student Session Access:** Pass HMAC-SHA256 token via `X-Session-Token: <token>` or `session_token` in body.
3. **Public Unauthenticated Access:** Callers without keys/tokens are strictly treated as `user_id = "guest"` to prevent user impersonation.

### Core Endpoints

#### 1. Public Chat (Interactive & Streaming)
* **`POST /chat`** (JSON) & **`POST /chat/stream`** (Server-Sent Events)
* **Rate Limit:** 15 requests/minute per client IP.
* **Payload:**
  ```json
  {
    "session_id": "sess_user123_turn1",
    "message": "What is an anxious-avoidant trap?",
    "user_id": "guest",
    "mode": "generic"
  }
  ```
* **Modes:**
  * `generic`: Pure clinical psychoeducation. Refuses commercial pitches.
  * `sales`: Consultative program advisor. Explains pattern and offers tailored course with pricing ($97) and checkout links.

#### 2. Discovery & Diagnostics (Protected)
* **`GET /health`** (Public): Returns sanitized readiness status (`qdrant`, `llm`, `documents`).
* **`GET /documents`** (Admin): Returns list of all 19 ingested clinical documents.
* **`GET /drive/status`** (Admin): Returns Google Drive connection and sync state.
* **`POST /drive/sync`** (Admin): Triggers an immediate re-scan of the Google Drive folder.
  ```bash
  curl -X POST https://agent.doctorsarahhensley.com/drive/sync -H "X-API-Key: dsh_rag_secret_key_2026"
  ```

#### 3. Administrative Cache Flushing
* **`POST /api/v1/cache/clear`** (Admin): Flushes both in-memory Semantic Query Cache and User Profile Cache.

---

## 5. Token Optimization & Guardrail Architecture

The generator layer ([`src/generator.py`](file:///c:/DSH%20RAG/RAG-DSH/src/generator.py)) includes four high-performance optimizations:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   4-LAYER LLM GENERATION SAFEGUARDS                    │
├──────────────────┬──────────────────┬──────────────────┬───────────────┤
│     Layer 1      │     Layer 2      │     Layer 3      │    Layer 4    │
│  Static Prompt   │ Dynamic Token    │ Layer 2 Greeting │ Layer 3 Fall- │
│  Prefix Caching  │ Headroom Ceilings│ Guardrail        │ back Trimmer  │
│  (50% Discount)  │ (250/700/800 Tok)│ (Hi {name},)     │ (No Cutoffs)  │
└──────────────────┴──────────────────┴──────────────────┴───────────────┘
```

1. **Static System Prompt Caching:**
   * System prompts in `_build_system_prompt()` are 100% byte-identical per lane.
   * Dynamic variables (user name, purchases, catalog) are injected cleanly in the user turn.
   * **Result:** OpenAI/Groq caches the system prompt, providing ~50% API cost discount and sub-second TTFT.
2. **Dynamic Headroom Ceilings (`effective_max_tokens`):**
   * **Short Definitions (<6 words):** `250 tokens` (~100 words).
   * **Clinical Nuanced (`generic`):** `700 tokens` (~350 words + structured takeaways).
   * **Program Advisor (`sales`):** `800 tokens` (~400 words + product card + checkout links).
3. **Layer 2 Deterministic Salutation Guardrail:**
   * **Turn 1:** Enforces `Hi {First Name},` on line 1.
   * **Turn 2+:** Automatically strips repetitive greetings on continuing turns.
4. **Layer 3 Graceful Truncation Trimmer (`clean_trailing_truncation`):**
   * Eliminates severed markdown headers (e.g. `**Practical`) or incomplete bullet points.
   * Automatically snaps text back to the last complete sentence ending in `.`, `!`, or `?`.

---

## 6. Scheduled Cron Tasks & Maintenance

Automated tasks run autonomously on the server via `crontab -l`:

```crontab
# 1. Nightly 2:00 AM - WordPress WooCommerce to MySQL Sync
0 2 * * * /home/ubuntu/DSH-RAG/venv/bin/python /home/ubuntu/DSH-RAG/scripts/sync_wordpress_to_mysql.py >> /home/ubuntu/DSH-RAG/logs/sync.log 2>&1

# 2. Nightly 3:00 AM - Automated Database Backups (SQLite & MySQL)
0 3 * * * /home/ubuntu/DSH-RAG/venv/bin/python /home/ubuntu/DSH-RAG/scripts/backup_databases.py --local-only >> /home/ubuntu/DSH-RAG/logs/backup.log 2>&1

# 3. Weekly Sunday 4:00 AM - Server Maintenance, Database Vacuuming & Log Pruning
0 4 * * 0 /home/ubuntu/DSH-RAG/venv/bin/python /home/ubuntu/DSH-RAG/scripts/run_maintenance.py >> /home/ubuntu/DSH-RAG/logs/maintenance.log 2>&1
```

### Log Rotation Policy (`/etc/logrotate.d/dsh-rag`)
* Rotates daily or whenever any file reaches **10MB**.
* Retains **7 compressed archives** (`.gz`), freeing ~90% disk space.
* Uses `copytruncate` so live chat streaming is never interrupted.

---

## 7. Knowledge Base & Google Drive Ingestion

* **Google Drive Folder ID:** `13iyfLkaWOvvw8JQVyzjw_YjTec9cZ_PG`
* **Credentials:** Service Account via `/home/ubuntu/DSH-RAG/service_account.json`
* **Status:** 19 documents currently `READY` in Qdrant collection `documents`.

### Adding a New Document
1. Upload the PDF or DOCX file to the designated Google Drive folder.
2. The background monitor checks the folder periodically, detects the new file, extracts text, generates MiniLM 384-dim embeddings, and upserts them to Qdrant.
3. To trigger indexing immediately, call the sync endpoint:
   ```bash
   curl -X POST https://agent.doctorsarahhensley.com/drive/sync \
     -H "X-API-Key: dsh_rag_secret_key_2026"
   ```

---

## 8. Incident Response & Disaster Recovery

### Common Scenarios

#### Scenario A: Service Fails to Start (`502 Bad Gateway`)
1. Check the systemd log:
   ```bash
   journalctl -u dsh-rag.service -n 50 --no-pager
   ```
2. Verify `.env` exists and contains `RAG_API_KEY` and LLM keys (`GROQ_API_KEY` or `OPENAI_API_KEY`).
3. Check if port 8000 is occupied:
   ```bash
   sudo lsof -i :8000
   ```
4. Restart the service:
   ```bash
   sudo systemctl restart dsh-rag.service
   ```

#### Scenario B: Qdrant Vector Search Returns Errors
1. Verify Qdrant is listening on localhost:
   ```bash
   curl -s http://127.0.0.1:6333/collections/documents | jq .status
   ```
2. If Qdrant is stopped, restart its service:
   ```bash
   sudo systemctl restart qdrant.service
   ```

#### Scenario C: Restoring Database from Nightly Backup
Daily compressed backups are stored in `/home/ubuntu/DSH-RAG/backups/`.
To restore a snapshot:
```bash
cd /home/ubuntu/DSH-RAG

# 1. Stop web service
sudo systemctl stop dsh-rag.service

# 2. Restore SQLite customer database
gunzip -c backups/users_data_YYYYMMDD_HHMMSS.db.gz > users_data.db

# 3. Restore MySQL database
gunzip -c backups/rag_users_YYYYMMDD_HHMMSS.sql.gz | mysql -u rag_user -p rag_users

# 4. Restart web service
sudo systemctl start dsh-rag.service
```

---

*Authored for the Dr. Sarah Hensley Engineering & Operations Team.*
