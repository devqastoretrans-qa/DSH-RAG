# ⚠️ Architectural Findings, Inconsistencies & Trust Boundary Analysis

This document outlines:
1. **Unverified items** and what external access is needed to confirm them.
2. **Inconsistencies** between user descriptions and actual code implementation.
3. **Trust boundary crossings** where sensitive data travels without encryption or authentication.

---

## 1. Unverified Items & Missing External Artifacts

| Item | What Is Unknown / Unverified | Evidence in Code | Access Needed to Verify |
| :--- | :--- | :--- | :--- |
| **"Levamo" Identity** | The exact name **"Levamo" does not appear in any file, comment, commit, or script** in this repository. | The only upstream systems in code are WordPress WooCommerce (`WORDPRESS_URL`) and the custom PAB plugin (`/wp-json/pab/v1/inspect/profile`). | Confirmation from project leadership on whether "Levamo" is the internal codename for the WordPress site, an external CRM, or the parent agency. |
| **WordPress PAB Plugin Internals** | How the `/wp-json/pab/v1/inspect/profile` endpoint processes Relationship Quiz answers, attachment scores, and streaks. | Only the client call in [`src/user_db.py:148`](file:///c:/DSH%20RAG/RAG-DSH/src/user_db.py#L148) is present; the server-side PHP plugin code is remote. | Read-only SSH/FTP access to the WordPress instance (`wp-content/plugins/`) or the plugin git repo. |
| **Google Cloud IAM & Drive Folder Sharing** | The exact IAM role grants for the service account and whether the Google Drive folder (`GOOGLE_DRIVE_FOLDER_ID`) is shared outside the domain. | `service_account.json` credentials exist, but cloud IAM policies are external. | Read access to Google Cloud Console (IAM & Admin) and Google Drive folder sharing settings. |
| **Production MySQL Privileges** | Whether the database user `rag_user` has `GRANT ALL PRIVILEGES` or is strictly bounded to `SELECT, INSERT, UPDATE, DELETE`. | [`scripts/setup_mysql.py:39`](file:///c:/DSH%20RAG/RAG-DSH/scripts/setup_mysql.py#L39) shows `GRANT ALL PRIVILEGES ON rag_users.*`. | Direct review of `SHOW GRANTS FOR 'rag_user'@'localhost';` on production MySQL. |

---

## 2. Inconsistencies Between Architecture Descriptions & Code

### A. "Levamo" &rarr; MySQL Data Path
* **Description:** Implies a direct data pipeline from a service called "Levamo" into MySQL.
* **Actual Code Implementation:** All data flowing into MySQL originates from **WordPress WooCommerce** via two distinct paths:
  1. Real-time push webhooks ([`app.py:1307`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L1307)).
  2. Nightly ETL pulling from the WooCommerce REST API ([`scripts/sync_wordpress_to_mysql.py`](file:///c:/DSH%20RAG/RAG-DSH/scripts/sync_wordpress_to_mysql.py)).
  There is no third-party adapter, microservice, or external database named Levamo present in the code.

### B. Server-Side vs. Client-Provided Conversation Memory
* **Description:** Multi-turn chat history is documented as managed strictly server-side in MySQL `conversation_turns`.
* **Actual Code Implementation:** In [`app.py:899`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L899), the API explicitly checks:
  ```python
  if request.chat_history is not None:
      chat_history = request.chat_history
  else:
      chat_history = conv_memory.get_chat_history(...)
  ```
  If a client passes `chat_history` directly in the JSON request body, the server completely bypasses its own database history and passes the client-provided list to the LLM.

### C. Personalization & User ID Resolution
* **Description:** User profile and past records are fetched automatically from MySQL based on authenticated session context.
* **Actual Code Implementation:** In [`SearchQueryRequest`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L225) and [`ChatRequest`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L247), the client can pass any arbitrary `user_id` string (defaulting to `"admin"` or `"guest"`), or pass an entire synthetic `user_profile` dictionary in the request body, bypassing MySQL lookups entirely.

---

## 3. Trust Boundary & Sensitive Data Exposure Analysis
*(Listed for audit visibility; no code changes made)*

1. **Third-Party LLM Provider Data Leakage:**
   * **Boundary:** EC2 Application Server &rarr; External Third-Party (OpenAI / Groq API).
   * **Observation:** User first names, attachment styles (e.g., *"Anxious-Preoccupied"*), owned courses, and clinical intake notes from `past_records` are concatenated into the prompt string and transmitted over the public internet to OpenAI (`api.openai.com`).
2. **Public Schema & Table Inspector Endpoints:**
   * **Boundary:** External Public Internet &rarr; Internal MySQL Database.
   * **Observation:** [`GET /api/schema`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L1210) and [`GET /api/schema/table/{table_name}`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L1253) are completely unauthenticated. Any external visitor can browse table structures and view raw database records in JSON.
3. **Unauthenticated Public Chat Routes:**
   * **Boundary:** Public Internet &rarr; RAG Engine & LLM.
   * **Observation:** [`POST /chat`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L1044), [`POST /chat/stream`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L1107), and [`POST /chat/reset`](file:///c:/DSH%20RAG/RAG-DSH/app.py#L1118) have no authentication or rate limiting.
4. **Sensitive Query Logging:**
   * **Boundary:** Memory &rarr; Local File System (`logs/application.log`).
   * **Observation:** In [`src/rag_service.py:178, 259, 289`](file:///c:/DSH%20RAG/RAG-DSH/src/rag_service.py#L178), full user query strings—often containing sensitive personal disclosures, infidelity details, or emotional crisis statements—are logged in plaintext to local disk log files.
