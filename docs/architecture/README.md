# 📚 System Architecture & Data Flow Documentation

Welcome to the comprehensive, evidence-based systems architecture documentation for the **Doctor Sarah Hensley AI (DSH-RAG)** platform.

All documentation and diagrams in this folder were produced through direct, read-only analysis of the live codebase, configuration schemas, SQL migrations, and synchronization scripts.

---

## 📑 Deliverables Directory

| File | Type | Description |
| :--- | :---: | :--- |
| **[`01_system_overview.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/01_system_overview.mmd)** | Mermaid Flowchart | End-to-end architecture flowchart showing trust boundaries, swimlanes, all modules, data stores, and external third parties. |
| **[`02_levamo_to_mysql_data_flow.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/02_levamo_to_mysql_data_flow.mmd)** | Mermaid Sequence | Detailed data movement between the upstream store ("Levamo" / WordPress / WooCommerce / PAB) &rarr; MySQL `rag_users` &rarr; RAG engine. |
| **[`03_chat_request_sequence.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/03_chat_request_sequence.mmd)** | Mermaid Sequence | Step-by-step trace of a live chat request from browser query to token streaming (crisis checks, memory, cache, search, LLM). |
| **[`04_ingestion_flow.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/04_ingestion_flow.mmd)** | Mermaid Flowchart | Complete document lifecycle from Google Drive & `/upload` through text extraction, chunking, and MiniLM embedding to Qdrant. |
| **[`05_data_transactions.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/05_data_transactions.mmd)** | Mermaid Flowchart | Visual topology of all 33 data transaction hops across clients, proxy, backend modules, and persistence stores. |
| **[`05_data_transactions.md`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/05_data_transactions.md)** | Technical Matrix | Comprehensive table of all data transactions mapping trigger, protocol, fields moved, sensitivity, auth, and code locations. |
| **[`06_api_inventory.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/06_api_inventory.mmd)** | Mermaid Topology | Complete visual API surface map showing all public, admin-secured, and webhook endpoints with outbound calls. |
| **[`06_api_inventory.md`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/06_api_inventory.md)** | Technical Catalog | Full catalog of all 23 endpoints exposed by FastAPI, and all 8 external APIs and internal datastores called by DSH-RAG. |
| **[`07_trust_boundaries_and_findings.mmd`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/07_trust_boundaries_and_findings.mmd)** | Mermaid Flowchart | Visual trust boundary map showing data crossings, unverified entities, and architectural inconsistencies. |
| **[`07_findings_and_unknowns.md`](file:///c:/DSH%20RAG/RAG-DSH/docs/architecture/07_findings_and_unknowns.md)** | Security & Arch Audit | Documented unverified items, code-vs-description inconsistencies, and sensitive data crossing trust boundaries without protection. |

---

## 🎨 How to Render the `.mmd` Diagrams

> **Notice Regarding Mermaid CLI (`mmdc`):**  
> The Mermaid CLI binary (`mmdc`) is **not installed** in this local host environment (`The term 'mmdc' is not recognized`). In accordance with architectural integrity rules, static images have not been faked or generated via external cloud converters.

You can render and view the diagrams in any of the following standard ways:

### Method 1: Using Mermaid Live Editor (Browser)
1. Open **[https://mermaid.live](https://mermaid.live)**.
2. Open any `.mmd` file in this directory and copy its text content.
3. Paste the content into the code pane on Mermaid Live.
4. Export as **SVG** or **PNG** with a single click.

### Method 2: In Antigravity IDE / VS Code
1. Install the extension **Markdown Preview Mermaid Support** or **Mermaid Previewer**.
2. Open any `.mmd` file in the editor and click the **Preview** button (`Ctrl + K, V`) to view the interactive diagram.

### Method 3: Compiling to SVG / PNG via Node CLI
If Node.js is available on your machine, compile all `.mmd` diagrams locally with:
```bash
# 1. Install Mermaid CLI globally
npm install -g @mermaid-js/mermaid-cli

# 2. Render each diagram to SVG
mmdc -i docs/architecture/01_system_overview.mmd -o docs/architecture/01_system_overview.svg
mmdc -i docs/architecture/02_levamo_to_mysql_data_flow.mmd -o docs/architecture/02_levamo_to_mysql_data_flow.svg
mmdc -i docs/architecture/03_chat_request_sequence.mmd -o docs/architecture/03_chat_request_sequence.svg
mmdc -i docs/architecture/04_ingestion_flow.mmd -o docs/architecture/04_ingestion_flow.svg
```
