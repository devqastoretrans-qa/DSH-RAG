# 🗄️ Database Schema & Relational Architecture (`rag_users`)

> **AWS EC2 MySQL 8.4** • Database: `rag_users`  
> Connected in **Antigravity IDE** via **SQLTools** (`AWS EC2 MySQL (rag_users)` on local port `3306`)

---

## 🗺️ Visual Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    users ||--o{ purchases : "user_id (ON DELETE CASCADE)"
    users ||--o{ past_records : "user_id (ON DELETE CASCADE)"
    users |o--o{ conversation_turns : "user_id (Logical Ref)"

    users {
        VARCHAR(50) id PK "WordPress ID (e.g. '1836') or Guest Email"
        VARCHAR(100) name "Full Name"
        VARCHAR(100) email "Unique Email Address"
        TIMESTAMP created_at "Account Creation Timestamp"
    }

    purchases {
        INT id PK "Auto Increment"
        VARCHAR(50) user_id FK "FK -> users.id (CASCADE)"
        VARCHAR(50) item_type "course, masterclass, or subscription"
        VARCHAR(255) item_title "Title of Purchased Item"
        TIMESTAMP purchased_at "Purchase Timestamp"
    }

    past_records {
        INT id PK "Auto Increment"
        VARCHAR(50) user_id FK "FK -> users.id (CASCADE)"
        VARCHAR(100) interaction_type "e.g. coaching_session, clinical_intake"
        TEXT summary_notes "Attachment style, background, notes"
        TIMESTAMP recorded_at "Record Timestamp"
    }

    conversation_turns {
        INT id PK "Auto Increment"
        VARCHAR(150) session_key "Indexed Session Identifier"
        VARCHAR(100) user_id "Current Active Persona / User"
        VARCHAR(100) conversation_id "UUID Conversation Group"
        VARCHAR(20) role "user or assistant"
        VARCHAR(50) mode "generic (Clinical) or sales (Advisor)"
        VARCHAR(255) topic "Discussion Topic / Intent"
        MEDIUMTEXT content "Full Turn Message (Markdown)"
        DOUBLE created_at "Unix Epoch Timestamp"
    }
```

---

## 🔍 How to View in Antigravity IDE

### Method 1: Using SQLTools Tree View
1. Click the **SQLTools icon** (cylinder with plug) in the Antigravity left Activity Bar.
2. Under **CONNECTIONS**, locate **`AWS EC2 MySQL (rag_users)`**.
3. Click the **Connect** (plug) icon.
4. Expand **`rag_users`** ➔ **`Tables`**.
5. Every table will automatically show:
   - 📁 **Columns** (with column type & PK key badge)
   - 📁 **Indexes** (Primary Key, unique keys, and composite indexes)
   - 📁 **Foreign Keys** (`fk_purchases_user` ➔ `users.id`, `fk_records_user` ➔ `users.id`)
6. Right-click any table ➔ **"Describe Table"** (or press `Ctrl+E Ctrl+D`) to open a dedicated visual schema inspector tab.
7. Right-click any table ➔ **"Show Table Records"** to inspect live tabular rows.

---

### Method 2: Running the Pre-Written Schema Inspector
Open [`scripts/inspect_schema.sql`](file:///c:/DSH%20RAG/RAG-DSH/scripts/inspect_schema.sql) in Antigravity IDE, select the connection **`AWS EC2 MySQL (rag_users)`**, and click **"Run on active connection"** (or press `Ctrl+E Ctrl+E`). It will output:
- Complete column definitions (data types, nullability, defaults)
- All foreign key relationships with parent/child mappings
- All indexes and uniqueness constraints
- Live record counts across all 4 tables

---

### Method 3: Live Studio Web Viewer
You can also view this interactive schema anytime with real-time statistics in the browser at:  
👉 **[https://agent.doctorsarahhensley.com](https://agent.doctorsarahhensley.com)** ➔ Click **`🗄️ Database Tables`** ➔ **`🗺️ Schema (ERD)`**.
