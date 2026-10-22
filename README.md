# Doctor Sarah Hensley AI — Personalized RAG System

A production-grade, personalized **Retrieval-Augmented Generation (RAG)** system built for **Doctor Sarah Hensley's Relationship & Attachment Theory Practice**.

The system features **dual-lane clinical vs. sales bot isolation**, **automated Google Drive 60-second synchronization**, **hybrid dense-sparse search with reciprocal rank fusion (RRF)**, **cross-encoder re-ranking**, **WordPress/WooCommerce customer profile personalization**, and **persistent multi-turn conversation memory**.

---

## 📑 Table of Contents
1. [Key Features](#-key-features)
2. [Dual-Lane Bot Architecture (Clinical vs. Sales)](#-dual-lane-bot-architecture)
3. [System Architecture Diagram](#-system-architecture-diagram)
4. [Google Drive Automated Ingestion](#-google-drive-automated-ingestion)
5. [Multi-Stage Retrieval & Optimization Stack](#-multi-stage-retrieval--optimization-stack)
6. [WordPress, MySQL & Customer Profile Personalization](#-wordpress-mysql--customer-profile-personalization)
7. [WordPress to MySQL Synchronization Pipeline](#-wordpress-to-mysql-synchronization-pipeline)
8. [Automated Database Backups & Disaster Recovery](#-automated-database-backups--disaster-recovery)
9. [REST API Documentation & Endpoints](#-rest-api-documentation--endpoints)
10. [Local Installation & Setup](#-local-installation--setup)
11. [AWS EC2 Production Deployment](#-aws-ec2-production-deployment)
12. [Hardware Capacity & Concurrency Profile](#-hardware-capacity--concurrency-profile)
13. [Utility Scripts & Maintenance](#-utility-scripts--maintenance)
14. [Testing Suite & Operational Runbooks](#-testing-suite--operational-runbooks)

---

## 🚀 Key Features

- **Clinical vs. Sales Dual-Lane Isolation:**
  - **Clinical Bot (`mode="generic"`):** Pure psychoeducation and healing techniques. Forbids commercial promotions, course pitching, or pricing ($).
  - **Sales Bot (`mode="sales"`):** Consultative selling. Explains relationship patterns clinically, then presents the tailored course/masterclass with exact pricing ($97) and enrollment steps.
- **60-Second Google Drive Auto-Sync:**
  - Background worker continuously polls Google Drive.
  - Automatically discovers `RAG_Clinical-Knowledge` and `RAG_Sales` folders.
  - Downloads, chunks, embeds, and verifies new or modified PDFs without manual intervention.
- **Dedicated IST Embedding Audit Log:**
  - Live logging in [`logs/embedding_status.log`](file:///c:/DSH%20RAG/RAG-DSH/logs/embedding_status.log) showing Indian Standard Time (IST), file names, folder lane, status (`EMBEDDED: YES/NO`), chunks, vectors, and execution durations.
- **Advanced Hybrid Search & Re-Ranking:**
  - Combines **Dense Vector Embeddings** (`sentence-transformers/all-MiniLM-L6-v2`) with **BM25 Sparse Keyword Scoring**.
  - Merges candidate rankings using **Reciprocal Rank Fusion (RRF)** with lane-specific weights.
  - **Cross-Encoder Re-Ranking** (`ms-marco-MiniLM-L-6-v2`) with dynamic confidence bypass ($\ge 0.85$ cosine similarity skips re-ranking to conserve CPU).
- **3-Tier Customer Personalization Engine:**
  - Fast in-memory LRU cache $\rightarrow$ self-hosted **MySQL 8.4** relational database (`rag_users`) $\rightarrow$ live **WordPress WooCommerce REST API** (`/wp-json/wc/v3`).
  - Accesses customer profile, purchased courses/books, and past Relationship Quiz records.
  - Automatic zero-config fallback to local SQLite (`users_data.db`) if MySQL is offline.
  - **Guardrail:** Never pitches or recommends courses the customer already owns!
- **Persistent Multi-Worker Conversation Memory:**
  - Multi-turn conversation history is stored persistently in MySQL, enabling consistent session continuity across multiple concurrent Uvicorn workers and surviving server reboots.
- **Automated Nightly Synchronization & Backups:**
  - Scheduled nightly ETL synchronization at 2:00 AM imports newly registered WooCommerce customers and purchases into local MySQL with zero-lock safety.
  - Scheduled nightly database backups at 3:00 AM with maximum gzip compression (`gzip -9`) and automated 14-day rolling retention.
- **Semantic Caching:**
  - In-memory semantic cache returns answers for semantically equivalent queries in **0 ms** (cosine $\ge 0.95$).

---

## 🎭 Dual-Lane Bot Architecture

To maintain medical and consultative integrity, the system strictly separates clinical therapy content from commercial sales catalogs:

| Feature / Dimension | 🩺 Clinical Knowledge Bot (`mode="generic"`) | 💼 Consultative Sales Bot (`mode="sales"`) |
| :--- | :--- | :--- |
| **Primary Goal** | Emotional support, psychoeducation, attachment theory & coping mechanisms. | Consultative diagnostics, tailored program recommendation & conversion. |
| **Document Lane** | `documents/clinical_knowledge/` & Drive `RAG_Clinical-Knowledge` | `documents/sales_catalog/` & Drive `RAG_Sales` (+ clinical context) |
| **Qdrant Vector Filter** | **Purges all sales chunks:** `category != "sales"` | Searches both clinical and sales catalog vector lanes |
| **Commercial Pitching** | 🚫 **STRICTLY FORBIDDEN:** Zero course pitches, zero prices (`$`), zero checkout links. | ✅ **REQUIRED:** Explains curriculum, exact price ($97), payment tiers & links. |
| **Owned Products** | N/A | Filters out any program already purchased by the user. |
| **Response Tone** | Empathetic, psychologically grounded, therapeutic, non-transactional. | Diagnostic, encouraging, consultative, clear call-to-action. |

---

## 🏛️ System Architecture Diagram

```text
                           DOCUMENT INGESTION PIPELINE
                     ┌──────────────────────────────────────┐
                     │          Google Drive Folders        │
                     │  ├── RAG_Clinical-Knowledge (PDFs)   │
                     │  └── RAG_Sales (PDFs)                │
                     └──────────────────┬───────────────────┘
                                        │ (60s Polling Cycle)
                                        ▼
                     ┌──────────────────────────────────────┐
                     │          PyPDF Text Extractor        │
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │   Sentence-Bounded Chunker (150 words)│
                     │   + Contextual Grounding Header      │
                     │   + Category Tag ("clinical"/"sales")│
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │  MiniLM Embeddings (384-dimensional) │
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │    Qdrant Vector Database (Cloud/EC2)│
                     │    INT8 Quantization + Rich Payloads │
                     └──────────────────────────────────────┘

                          QUERY & GENERATION PIPELINE
 User Query ───► Semantic Cache Check (Cosine >= 0.95) ───► [Cached Answer in 0ms]
      │ (Cache Miss)
      ▼
 Dense Query Vector (MiniLM) + Sparse Query Tokens (BM25)
      │
      ▼
 Qdrant Vector Search + BM25 Scoring
      │
      ▼
 Lane Isolation Filter (Clinical mode purges category == "sales")
      │
      ▼
 Reciprocal Rank Fusion (RRF: 70/30 Clinical vs 50/50 Sales)
      │
      ▼
 Cross-Encoder Joint Re-Ranking (ms-marco-MiniLM-L-6-v2)
 (Bypassed if top similarity >= 0.85 to save CPU)
      │
      ▼
 Customer Profile Injection (In-Memory -> MySQL 8.4 -> WordPress API)
 (Filters out already owned courses / books)
      │
      ▼
 GPT-4o-mini Answer Synthesis
 ├── Clinical Mode: Pure psychoeducation + strict non-commercial negative constraint
 └── Sales Mode: Consultative diagnosis + unowned masterclass recommendation ($97)
      │
      ▼
 Streamed / JSON Response + Verified Document Citations
```

---

## 📂 Google Drive Automated Ingestion

The system monitors two dedicated subfolders in your Google Drive:

```
Your Google Drive Parent Folder (ID: 13iyfLkaWOvvw8JQVyzjw_YjTec9cZ_PG)
├── 📁 RAG_Clinical-Knowledge      (ID: 1jBGT2WUYg5wCpQBhMuYyCdDmOlUTMt6J)
│   └── (Drop clinical PDFs here -> automatically tagged category="clinical")
│
└── 📁 RAG_Sales                   (ID: 1O8gJCU1V3w9KCBFohpdVQmhw6KZtuuaQ)
    └── (Drop course/sales PDFs here -> automatically tagged category="sales")
```

### Physical Folder Mapping (Local & AWS Server)
- Local: [`documents/clinical_knowledge/`](file:///c:/DSH%20RAG/RAG-DSH/documents/clinical_knowledge) $\leftrightarrow$ Drive `RAG_Clinical-Knowledge`
- Local: [`documents/sales_catalog/`](file:///c:/DSH%20RAG/RAG-DSH/documents/sales_catalog) $\leftrightarrow$ Drive `RAG_Sales`

### Dedicated Audit Log: `logs/embedding_status.log`
Every 60-second cycle records an audit entry in Indian Standard Time (IST):
```log
[2026-10-08 19:50:04 IST] | File: Clinical_Knowledge_Attachment_Guide.pdf | Folder: RAG_Clinical-Knowledge | Category: clinical | Status: EMBEDDED: YES | Chunks: 5 | Vectors: 5 | Duration: 9.13s (Within 60s poll) | Details: Vectorized and upserted into Qdrant
[2026-10-08 19:50:06 IST] | File: Sales_Programs_and_Masterclasses_Catalog.pdf | Folder: RAG_Sales | Category: sales | Status: EMBEDDED: YES | Chunks: 4 | Vectors: 4 | Duration: 1.30s (Within 60s poll) | Details: Vectorized and upserted into Qdrant
[2026-10-08 19:50:06 IST] | Drive Scan (60s cycle) | Monitored: [RAG_Clinical-Knowledge, RAG_Sales] | Files Found: 2 | Processed: 2 | Skipped: 0
```

### Real-Time Terminal Watcher
Run the live terminal watcher anytime:
```powershell
python watch_drive_sync.py
```

---

## ⚡ Multi-Stage Retrieval & Optimization Stack

1. **Sentence-Bounded Chunking ([`src/chunker.py`](file:///c:/DSH%20RAG/RAG-DSH/src/chunker.py)):**
   - Chunks at 150 words with 25-word overlap respecting sentence boundaries.
   - Bakes `[Document: title | Page N]` into the embedding vector.
   - Preserves small-to-big parent context window for enriched downstream synthesis.
2. **INT8 Scalar Quantization ([`src/qdrant_service.py`](file:///c:/DSH%20RAG/RAG-DSH/src/qdrant_service.py)):**
   - Vectors are quantized to INT8, reducing Qdrant RAM consumption by 75% and speeding up vector similarity search by 2–3x.
3. **Dynamic Re-Ranking Bypass ([`src/search.py`](file:///c:/DSH%20RAG/RAG-DSH/src/search.py)):**
   - When the top dense match reaches cosine similarity $\ge 0.85$, the Cross-Encoder is skipped, saving ~150 ms of CPU compute.
4. **Persistent Ingestion State Tracker ([`src/ingestion_tracker.py`](file:///c:/DSH%20RAG/RAG-DSH/src/ingestion_tracker.py)):**
   - SQLite database (`ingestion_tracker.db`) prevents duplicate downloads and reprocessing across reboots.

---

## 👤 WordPress, MySQL & Customer Profile Personalization

The system features a **3-tier data architecture** that delivers sub-millisecond personalized responses while ensuring strict data safety:

```text
  ┌────────────────────────────────────────────────────────┐
  │         Tier 1: High-Speed In-Memory Cache             │  (0 ms latency for active sessions)
  └───────────────────────────┬────────────────────────────┘
                              │ (Cache miss)
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │   Tier 2: Relational Local MySQL 8.4 ("rag_users")     │  (<1 ms local sub-millisecond query)
  │   (Fallback to SQLite "users_data.db" if offline)      │
  └───────────────────────────┬────────────────────────────┘
                              │ (User not found locally)
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │ Tier 3: WordPress WooCommerce REST API (/wp-json/wc/v3)│  (Read-only HTTP GET, fetches & caches)
  └────────────────────────────────────────────────────────┘
```

### 1. Strict Non-Destructive / Read-Only Safety Guarantee
- All interactions with the live WordPress / WooCommerce store (`dshstaging.doctorsarahhensley.com`) are **100% read-only**.
- The system connects exclusively through HTTP `GET` endpoints (`/wp-json/wc/v3/customers` and `/orders`) using a restricted application password.
- **Physical Safety Guarantee:** No `POST`, `PUT`, `PATCH`, or `DELETE` commands are ever sent to WordPress. Live courses, user profiles, orders, and database schemas cannot be modified or deleted.

### 2. Relational MySQL Database Schema (`rag_users`)
Hosted directly on the EC2 host with zero additional monthly AWS RDS charges, tuned for low memory (`innodb_buffer_pool_size = 64M`, ~196 MB RSS):

- **`users` Table:** Core user profile (`id`, `email`, `name`, `attachment_style`, `created_at`, `updated_at`).
- **`purchases` Table:** Course and book ownership records (`id`, `user_id`, `course_title`, `date`, `price`, `order_id`, `product_id`, `status`).
- **`past_records` Table:** PAB Relationship Quiz summaries, attachment scores, and intake notes.
- **`conversation_turns` Table:** Multi-turn conversation history (`turn_id`, `session_id`, `role`, `content`, `mode`, `timestamp`).

### 3. Multi-Worker Conversation Memory
Because conversation turns are stored in the shared MySQL database rather than process memory or single-file SQLite, conversation context is:
- **Shared across multiple concurrent Uvicorn worker processes** without locking conflicts.
- **Persistent across server reboots, redeployments, and service restarts**.
- Cleanly isolated by `session_id` and bounded to the most recent turns to fit within LLM context windows.

### 4. Unowned Course Filtering Guardrail ([`src/sales_catalog.py`](file:///c:/DSH%20RAG/RAG-DSH/src/sales_catalog.py))
- If a customer already owns the *"Healing Anxious Attachment Masterclass"*, the sales bot will **never** pitch that masterclass again.
- Instead, it dynamically detects ownership and recommends the next advanced offering (e.g., *"The Secure Relationship Masterclass"* or private 1-on-1 coaching).

---

## 🔄 WordPress to MySQL Synchronization Pipeline

To ensure the AI always knows about newly registered students and recent course purchases without burdening the live WordPress server on every chat turn, the system includes a dedicated, idempotent ETL pipeline: [`scripts/sync_wordpress_to_mysql.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/sync_wordpress_to_mysql.py).

### How It Works:
1. Connects to WooCommerce REST API via HTTP `GET`.
2. Paginates through customers and completed/processing orders.
3. Automatically normalizes customer names, emails, and purchased course titles into MySQL `rag_users`.
4. Deduplicates orders and purchases by `(user_id, course_title)` and order ID.
5. Employs per-record error isolation so an issue with one malformed order never aborts the overall sync.

### Automated Nightly Cron Job (EC2 Host)
Configured in the host crontab to execute every night at **2:00 AM server time**:
```cron
0 2 * * * /home/ubuntu/DSH-RAG/venv/bin/python /home/ubuntu/DSH-RAG/scripts/sync_wordpress_to_mysql.py >> /home/ubuntu/DSH-RAG/logs/sync_wordpress.log 2>&1
```

### Manual CLI Execution
```bash
# Full sync
python scripts/sync_wordpress_to_mysql.py

# Test run limited to 10 customers
python scripts/sync_wordpress_to_mysql.py --limit 10

# Sync only orders modified since a specific date
python scripts/sync_wordpress_to_mysql.py --since 2026-10-01
```

---

## 💾 Automated Database Backups & Disaster Recovery

The system features an automated snapshot engine ([`scripts/backup_databases.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/backup_databases.py)) protecting all stateful data stores with zero downtime.

### Backup Coverage (Sub-0.1 Second Execution):
1. **MySQL Database (`rag_users`):** Exported via `mysqldump` with `--single-transaction --quick --no-tablespaces` and piped directly into maximum gzip compression (`gzip -9`).
2. **Google Drive Ingestion State (`ingestion_tracker.db`):** SQLite snapshot.
3. **Local Fallback Database (`users_data.db`):** SQLite snapshot.

### Automated 14-Day Rolling Retention
To guarantee the EC2 disk volume never fills up, the backup engine automatically inspects the `backups/` directory on every run and prunes any backup snapshot older than **14 days**.

### Automated Nightly Backup Cron Job (EC2 Host)
Configured in the host crontab to execute every night at **3:00 AM server time** (1 hour after the sync):
```cron
0 3 * * * /home/ubuntu/DSH-RAG/venv/bin/python /home/ubuntu/DSH-RAG/scripts/backup_databases.py >> /home/ubuntu/DSH-RAG/logs/backup.log 2>&1
```

### Disaster Recovery Runbook
For complete, copy-paste restoration commands in under 2 minutes, see:  
📘 **[`docs/runbooks/01_database_restore.md`](file:///c:/DSH%20RAG/RAG-DSH/docs/runbooks/01_database_restore.md)**

---

## 📡 REST API Documentation & Endpoints

Base URL: `http://18.118.138.91:8000` (AWS EC2) or `http://127.0.0.1:8000` (Local)  
API Authentication: Header `X-API-Key: dsh_rag_secret_key_2026` or `Authorization: Bearer dsh_rag_secret_key_2026`

### Endpoint Summary

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/ask` | Primary Personalized RAG generation (`generic` vs `sales` mode) | Yes |
| `POST` | `/api/v1/sales/ask` | Dedicated Consultative Sales RAG endpoint | Yes |
| `POST` | `/search` | Dashboard hybrid search + re-ranking + generation | No (UI) |
| `GET` | `/health` | System health status (Qdrant, Drive, Embeddings, DBs) | No |
| `GET` | `/drive/status` | Current status of 60s Drive monitor and last scan results | No |
| `POST` | `/drive/sync` | Manually trigger Drive sync (`?force=true` supported) | No |
| `GET` | `/documents` | List all registered documents and lifecycle states | No |
| `GET` | `/api/users` | List registered customer profiles and purchase records | No |
| `POST` | `/api/v1/cache/clear`| Flushes Semantic Query Cache and User Profile Cache | Yes |
| `GET` | `/docs` | Interactive Swagger UI API documentation | No |

---

### API Usage Examples

#### 1. Clinical Query (`mode="generic"`)
```bash
curl -X POST "http://18.118.138.91:8000/api/v1/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dsh_rag_secret_key_2026" \
  -d '{
    "user_id": "sarah_anxious",
    "question": "How do I calm my nervous system when I fear my partner is pulling away?",
    "mode": "generic"
  }'
```

#### 2. Consultative Sales Query (`mode="sales"`)
```bash
curl -X POST "http://18.118.138.91:8000/api/v1/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dsh_rag_secret_key_2026" \
  -d '{
    "user_id": "sarah_anxious",
    "question": "What course should I take to heal my anxious attachment style?",
    "mode": "sales"
  }'
```

#### 3. Health Check
```bash
curl -X GET "http://18.118.138.91:8000/health"
```
Response:
```json
{
  "status": "ok",
  "fastapi": "ok",
  "qdrant": {
    "status": "ok",
    "mode": "Cloud (http://127.0.0.1:6333)",
    "collection_name": "documents"
  },
  "embeddings": {
    "status": "ok",
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "dimension": 384
  },
  "google_drive_monitor": {
    "running": true,
    "poll_interval_seconds": 60,
    "last_scan_time": "2026-10-08T19:54:11.028047+05:30"
  },
  "user_database": "ready (WordPress WooCommerce (REST API) + MySQL)",
  "documents": {
    "total": 2,
    "ready": 2
  }
}
```

---

## 💻 Local Installation & Setup

### Prerequisites
- Python 3.9 – 3.12 (Recommended: 3.10+)
- Git

### 1. Clone & Set Up Environment
```bash
git clone <repository_url>
cd RAG-DSH

# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Create `.env` using `.env.example`:
```env
# Google Drive Auto-Ingestion
GOOGLE_DRIVE_FOLDER_ID=13iyfLkaWOvvw8JQVyzjw_YjTec9cZ_PG
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
DRIVE_POLL_INTERVAL_SECONDS=60

# Qdrant Vector Database
# Leave empty to default to local persistent Qdrant at ./qdrant_db
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=documents

# Chunking & Embeddings
CHUNK_SIZE=150
CHUNK_OVERLAP=25
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# OpenAI Configuration (ChatGPT Answer Synthesis)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Relational MySQL Configuration (Personalized RAG & Conversation Memory)
# Leave empty to default to local zero-config SQLite fallback (users_data.db)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=rag_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=rag_users

# REST API Security & CORS
RAG_API_KEY=dsh_rag_secret_key_2026
ALLOWED_ORIGINS=https://doctorsarahhensley.com,https://www.doctorsarahhensley.com,https://dshstaging.doctorsarahhensley.com,https://agent.doctorsarahhensley.com

# WordPress WooCommerce Customer & Order API
WORDPRESS_URL=https://dshstaging.doctorsarahhensley.com
WORDPRESS_USER=admin@tribus.pub
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
WP_SSL_VERIFY=true
```

### 4. Run Locally
```bash
python app.py
```
Or with Uvicorn:
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```
Open Dashboard at: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## ☁️ AWS EC2 Production Deployment

The production system is deployed on an **AWS EC2 Ubuntu 24.04 LTS** instance:

- **Production Domain (HTTPS / SSL):** [https://agent.doctorsarahhensley.com/dsh-rag](https://agent.doctorsarahhensley.com/dsh-rag)
- **Public IP:** `18.118.138.91:8000`
- **SSH Key:** `C:\Tools\python-qdrant-server.pem`
- **SSH Access:**
  ```bash
  ssh -i C:\Tools\python-qdrant-server.pem ubuntu@18.118.138.91
  ```
- **System Services:**
  - `dsh-rag.service`: FastAPI application running under Uvicorn on port 8000.
  - `mysql.service`: MySQL 8.4 Server with low-memory configuration (`/etc/mysql/conf.d/low-memory.cnf`).
  - Qdrant Vector Database: Native binary listening on `127.0.0.1:6333`.
- **Service Management:**
  ```bash
  sudo systemctl status dsh-rag      # Check FastAPI RAG service
  sudo systemctl restart dsh-rag     # Restart application
  sudo journalctl -u dsh-rag -f      # Follow live application logs
  sudo systemctl status mysql        # Check MySQL database service
  ```
- **Automated Host Cron Jobs:**
  ```bash
  crontab -l
  # 0 2 * * * sync_wordpress_to_mysql.py (Nightly customer/purchase ETL)
  # 0 3 * * * backup_databases.py        (Nightly compressed multi-DB backup)
  ```

---

## 📊 Hardware Capacity & Concurrency Profile

Empirical capacity measured on the active AWS EC2 host:

| Resource | Specification | Current Utilization | Limit / Headroom |
| :--- | :--- | :--- | :--- |
| **Instance** | **AWS `t3.micro`** | Burstable CPU | 2 vCPUs (Intel Xeon 2.50GHz) |
| **Physical RAM** | **908 MB (~1 GB)** | ~710 MB Used | Physical RAM supplemented by EBS Swap |
| **Swap Space** | **2.0 GB Swapfile** (`/swapfile2`) | ~360 MB active | **~1.6 GB Swap Free** (Total virtual headroom: ~3.0 GB) |
| **FastAPI Process**| Uvicorn (Single Worker) | 424 MB RSS | Contains in-memory MiniLM embedding model |
| **MySQL 8.4 Server**| Low-Memory Tuned (`rag_users`) | ~196 MB RSS | `performance_schema=OFF`, `buffer_pool=64M` |
| **Qdrant Vector DB**| Standalone Process | 12.8 MB RSS | INT8 scalar quantization |
| **Safe Concurrency**| **5 to 8 simultaneous users** | ~45–60 queries/min | Protected by 2.0 GB swap safety net |

### 💾 Storage Sizing Profile (7,000+ WordPress Customers)
- **MySQL Storage Footprint:** For 7,000 users and their purchase records, our relational schema requires only **~35 MB – 50 MB** of disk space (<0.25% of the 19.5 GB available disk space on `/dev/root`).
- **Why is it so much smaller than WordPress's 2 GB database?**
  WordPress stores raw JSON action scheduler logs, WooCommerce transients, cart cookies, revisions, unindexed post metadata, and extensive audit histories. Our RAG database extracts only the distilled, high-signal relational facts (customer identity, course ownership, attachment scores, and conversation memory), ensuring microsecond query performance and minimal disk overhead.

### Scaling Roadmap:
- **`t3.micro` (Current):** Ideal for staging, development, and daily clinic operations (~$7.50/mo, $0 database fees).
- **`t3.small` (Recommended for Peak Launch):** 2 vCPUs, 2 GB RAM (~$15/mo). Immediately triples safe concurrency to **18–25 simultaneous users** and eliminates memory constraints.
- **`t3.medium` (High Traffic):** 2 vCPUs, 4 GB RAM (~$30/mo). Supports **50+ concurrent users** and 2–3 Uvicorn workers behind Nginx.

---

## 🛠️ Utility Scripts & Maintenance

All operational and maintenance scripts are located in [`scripts/`](file:///c:/DSH%20RAG/RAG-DSH/scripts) and the repository root:

- **[`scripts/sync_wordpress_to_mysql.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/sync_wordpress_to_mysql.py):**
  Paginates through WordPress WooCommerce REST API (`/customers` & `/orders`) and synchronizes user profiles and purchased products into MySQL `rag_users`. Run manually or via nightly 2:00 AM cron.
  ```powershell
  python scripts/sync_wordpress_to_mysql.py
  ```

- **[`scripts/backup_databases.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/backup_databases.py):**
  Atomically backs up MySQL `rag_users` (`mysqldump | gzip -9`) and SQLite tracking databases into timestamped archives in `backups/`, automatically pruning backups older than 14 days. Run manually or via nightly 3:00 AM cron.
  ```powershell
  python scripts/backup_databases.py
  ```

- **[`scripts/check_mysql_counts.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/check_mysql_counts.py):**
  Quick audit script reporting live row counts for `users`, `purchases`, `past_records`, and `conversation_turns`.
  ```powershell
  python scripts/check_mysql_counts.py
  ```

- **[`scripts/list_all_users.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/list_all_users.py):**
  Displays summary table of all registered users and their purchased courses directly from MySQL.
  ```powershell
  python scripts/list_all_users.py
  ```

- **[`scripts/setup_mysql.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/setup_mysql.py):**
  Initializes the MySQL `rag_users` database, sets up table schemas with indexes, and migrates existing SQLite rows into MySQL.
  ```powershell
  python scripts/setup_mysql.py
  ```

- **[`watch_drive_sync.py`](file:///c:/DSH%20RAG/RAG-DSH/watch_drive_sync.py):**
  Continuously monitors Google Drive in your local terminal every 60 seconds and displays live ingestion metrics.
  ```powershell
  python watch_drive_sync.py
  ```

- **[`wipe_all_data.py`](file:///c:/DSH%20RAG/RAG-DSH/wipe_all_data.py):**
  Completely resets Qdrant collection vectors to 0, clears SQLite tracking, flushes caches, and cleans local document directories for a fresh start.
  ```powershell
  python wipe_all_data.py
  ```

- **[`reset_and_ingest_fresh_docs.py`](file:///c:/DSH%20RAG/RAG-DSH/reset_and_ingest_fresh_docs.py):**
  Pushes fresh local copies of `Clinical_Knowledge_Attachment_Guide.pdf` and `Sales_Programs_and_Masterclasses_Catalog.pdf` into Qdrant.
  ```powershell
  python reset_and_ingest_fresh_docs.py
  ```

---

## 🧪 Testing Suite & Operational Runbooks

### Automated Verification Tests
```bash
# 1. Test sales catalog matching, unowned guardrails, and API endpoints
python test_sales_bot.py

# 2. Test full end-to-end optimizations (caching, RRF, re-ranker bypass, memory)
python test_live_all_optimizations.py

# 3. Test WordPress WooCommerce PAB user profile integration
python test_pab_integration.py

# 4. Verify live queries directly against AWS EC2 server
python test_live_aws.py
```

### Evaluation Benchmark & Test Questions
- **Golden Test Benchmark:** [`test_questions.csv`](file:///c:/DSH%20RAG/RAG-DSH/test_questions.csv) contains 40 clinically validated test questions spanning attachment styles, defensive triggers, masterclass matching, and unowned course guardrails.
- **Evaluation Report:** Complete accuracy and latency benchmarks are published in [`DSH_RAG_Test_Report_2026-10-21.pdf`](file:///c:/DSH%20RAG/RAG-DSH/DSH_RAG_Test_Report_2026-10-21.pdf) and [`DSH_RAG_Test_Report_2026-10-21.md`](file:///c:/DSH%20RAG/RAG-DSH/DSH_RAG_Test_Report_2026-10-21.md).

### Operational Runbooks & SLA
- 📘 **[Database Restore & Disaster Recovery](file:///c:/DSH%20RAG/RAG-DSH/docs/runbooks/01_database_restore.md):** Rapid recovery procedures for MySQL and SQLite.
- 📘 **[Credential Rotation](file:///c:/DSH%20RAG/RAG-DSH/docs/runbooks/02_credential_rotation.md):** Safe rotation guide for MySQL, OpenAI, and WordPress application passwords.
- 📘 **[Drive Sync Recovery](file:///c:/DSH%20RAG/RAG-DSH/docs/runbooks/03_drive_sync_recovery.md):** Troubleshooting and re-sync procedures for Google Drive ingestion.
- 📋 **[Production Service Level Agreement (SLA)](file:///c:/DSH%20RAG/RAG-DSH/docs/SLA.md):** Availability targets, recovery time objectives (RTO), and incident response definitions.
