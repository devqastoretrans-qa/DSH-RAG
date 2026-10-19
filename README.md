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
6. [WordPress & Customer Profile Personalization](#-wordpress--customer-profile-personalization)
7. [REST API Documentation & Endpoints](#-rest-api-documentation--endpoints)
8. [Local Installation & Setup](#-local-installation--setup)
9. [AWS EC2 Production Deployment](#-aws-ec2-production-deployment)
10. [Hardware Capacity & Concurrency Profile](#-hardware-capacity--concurrency-profile)
11. [Utility Scripts & Maintenance](#-utility-scripts--maintenance)
12. [Testing Suite](#-testing-suite)

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
- **Customer Personalization Engine:**
  - Integrates with WordPress WooCommerce REST API and local SQLite cache (`users_data.db`).
  - Accesses customer profile, purchased courses/books, and past Relationship Quiz records.
  - **Guardrail:** Never pitches or recommends courses the customer already owns!
- **Semantic Caching & Memory:**
  - In-memory semantic cache returns answers for semantically equivalent queries in **0 ms** (cosine $\ge 0.95$).
  - Multi-turn conversation memory maintains contextual continuity across user interactions.

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
 Customer Profile Injection (WordPress WooCommerce / Quiz Records)
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

## 👤 WordPress & Customer Profile Personalization

The system integrates with WordPress WooCommerce REST API and PAB quiz profiles:

- **Customer Data Tracked:** Name, email, purchased courses, purchased books, quiz-derived attachment style (e.g., *Anxious-Preoccupied*), past quiz notes.
- **Unowned Filtering Guardrail ([`src/sales_catalog.py`](file:///c:/DSH%20RAG/RAG-DSH/src/sales_catalog.py)):**
  - If user owns *"Healing Anxious Attachment Masterclass"*, the sales bot will **never** pitch that masterclass again; instead, it recommends the next advanced program (e.g., *"The Secure Relationship Masterclass"* or 1-on-1 coaching).

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

# REST API Security
RAG_API_KEY=dsh_rag_secret_key_2026
ALLOWED_ORIGINS=*

# WordPress WooCommerce API
WORDPRESS_URL=https://dshstaging.doctorsarahhensley.com
WORDPRESS_USER=admin@tribus.pub
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
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
- **Service Management:**
  ```bash
  sudo systemctl status dsh-rag      # Check service status
  sudo systemctl restart dsh-rag     # Restart application
  sudo journalctl -u dsh-rag -f      # Follow live application logs
  ```

---

## 📊 Hardware Capacity & Concurrency Profile

Empirical capacity measured on the active AWS EC2 host:

| Resource | Specification | Current Utilization | Limit / Headroom |
| :--- | :--- | :--- | :--- |
| **Instance** | **AWS `t3.micro`** | Burstable CPU | 2 vCPUs (Intel Xeon 2.50GHz) |
| **Physical RAM** | **908 MB (~1 GB)** | 696 MB (76.6% Used) | ~212 MB Free |
| **FastAPI Process**| Uvicorn (Single Worker) | 424 MB RSS | Contains in-memory embedding model |
| **Qdrant Vector DB**| Standalone Process | 12.8 MB RSS | INT8 scalar quantization |
| **Safe Concurrency**| **3 to 5 simultaneous users** | ~35–45 queries/min | Primary constraint: RAM |

### Scaling Roadmap:
- **`t3.micro` (Current):** Ideal for staging, development, and single-user admin testing (~$7.50/mo).
- **`t3.small` (Recommended for Launch):** 2 vCPUs, 2 GB RAM (~$15/mo). Immediately triples safe concurrency to **12–18 simultaneous users** and eliminates memory constraints.
- **`t3.medium` (High Traffic):** 2 vCPUs, 4 GB RAM (~$30/mo). Supports **30–45 concurrent users** and 2–3 Uvicorn workers behind Nginx.

---

## 🛠️ Utility Scripts & Maintenance

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

## 🧪 Testing Suite

Automated verification tests located in the root directory:

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
