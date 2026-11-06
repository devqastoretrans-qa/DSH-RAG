# Doctor Sarah Hensley AI RAG Ecosystem — Timesheet & Delivery Package

This directory contains the client-ready delivery timesheet, engineering evaluation, and delivery plan for building the AI agent suite (*Track 4: The AI Dependency Web*).

---

### Primary Deliverable
- **Excel Workbook:** [`timesheet_output/Agents_Delivery_Timesheet.xlsx`](file:///c:/DSH%20RAG/RAG-DSH/timesheet_output/Agents_Delivery_Timesheet.xlsx)
  - Unified **Sprint 1 only** delivery timesheet.
  - Fully formatted with corporate typography (Calibri), zebra striping, auto-fitted columns, landscape printing setup, live Excel formulas (`SUM`), and native openpyxl chart visualization.

---

### Sprint 1 Scope: All 8 Client Deliverables (Due 18-Nov-2026)
All 8 client deliverables—including **`AWS Load Balancer & Server Upgrade`** and **`ElevenLabs Integration`**—are scheduled inside **Sprint 1** and completed by **Wednesday, 18 November 2026**:

| # | Exact Task Name (As Given by Client) | Verbatim Client Scope & Description | Timesheet Task ID | Scheduled Date | Planned Hours |
|---|---|---|---|---|---|
| 1 | **Set Up the Agent on the Chat Page** | *Set up agent selector tabs/dropdown in templates/index.html UI to switch between Platform, Owner, Learning, and Coaching modes.* | `TSK-05` | Wed 11-Nov-2026 | 1.5 hrs |
| 2 | **Implement Chat History Storage** | *Store and manage chat history similar to ChatGPT; wire sidebar drawer with /api/chat/history.* | `TSK-10` | Thu 12-Nov-2026 | 1.5 hrs |
| 3 | **Token Management** | *Implement and optimize token usage and management (DEF-08 1,200 token cap & sliding window context memory).* | `TSK-15` | Fri 13-Nov-2026 | 0.5 hr |
| 4 | **Working on Documentation for the Mind** | *Author comprehensive cognitive guide docs/MIND_SPECIFICATION.md detailing Dr. Sarah Hensley's mental framework.* | `TSK-16` | Fri 13-Nov-2026 | 1.0 hr |
| 5 | **Create Do’s and Don’ts for the Mind** | *Author clinical guardrail rules docs/MIND_DOS_AND_DONTS.md: establishing what the Mind answers vs. clinical boundaries.* | `TSK-21` | Mon 16-Nov-2026 | 1.0 hr |
| 6 | **AWS Load Balancer & Server Upgrade** | *Configure the AWS Load Balancer and upgrade the server infrastructure (ALB target group, health check /health, port 8000 routing).* | `TSK-23` | Tue 17-Nov-2026 | 2.5 hrs |
| 7 | **ElevenLabs Integration** | *Integrate ElevenLabs for voice-related functionality (Text-to-speech API call, audio streaming, UI playback widget).* | `TSK-24` | Tue 17-Nov-2026 | 2.0 hrs |
| 8 | **AI Model Integration** | *Currently using Grok due to its free availability. We will switch to OpenAI once initial phase is completed (dual fallback test).* | `TSK-25` | Tue 17-Nov-2026 | 0.5 hr |

---

### Daily Schedule & Capacity Breakdown (6.0 hrs/day = 36.0 hrs Total)
* **Wednesday, 11-Nov (6.0h):** Platform Agent (`TSK-01` to `TSK-04`) + **`Set Up the Agent on the Chat Page`** (`TSK-05`)
* **Thursday, 12-Nov (6.0h):** Owner Agent (`TSK-06` to `TSK-09`) + **`Implement Chat History Storage`** (`TSK-10`)
* **Friday, 13-Nov (6.0h):** Learning Agent (`TSK-11` to `TSK-14`) + **`Token Management`** (`TSK-15`) + **`Working on Documentation for the Mind`** (`TSK-16`)
* **Monday, 16-Nov (6.0h):** Coaching Agent (`TSK-17` to `TSK-20`) + **`Create Do’s and Don’ts for the Mind`** (`TSK-21`) + Async DB Fix (`TSK-22`)
* **Tuesday, 17-Nov (6.0h):** **`AWS Load Balancer & Server Upgrade`** (`TSK-23`) + **`ElevenLabs Integration`** (`TSK-24`) + **`AI Model Integration`** (`TSK-25`) + Ingestion Fix (`TSK-26`) + Runbook Specs (`TSK-27`)
* **Wednesday, 18-Nov (6.0h):** Automated QA Suite (`TSK-28`) + EC2 Production Go-Live (`TSK-29`) + Live Smoke Tests (`TSK-30`) + Client Acceptance Demo (`TSK-31`)

---

### Workbook Sheet Structure (10 Formatted Sheets)
1. **`Summary`**: Executive scorecard, key dates, all-inclusive Sprint 1 status snapshot, and delivery verdict.
2. **`Agent Status`**: Systematic audit of all 7 architecture components with exact file paths, lines, and remaining work.
3. **`Production Readiness`**: 11-category audit of cloud deployment, AWS ALB, ElevenLabs voice, secrets, vector DB, reliability, and CI/CD.
4. **`Timesheet`**: Granular breakdown of 31 tasks (`TSK-01` to `TSK-31`) all in Sprint 1 with dynamic formula `=SUM(G6:G36)` = 36.0 hours.
5. **`Day-by-Day Plan`**: Daily milestones and hourly subtotals (`=SUM(E5:E12)` = 36.0h) across all 6 working days.
6. **`Hours Summary`**: Workload rollups by deliverable, capacity reconciliation, and openpyxl Bar Chart visualization.
7. **`Parallel vs Sequential`**: Critical path analysis establishing prerequisite chains leading to 18-Nov release.
8. **`Go-Live Checklist`**: Operational acceptance criteria for all 8 client items and core agents.
9. **`Risks & Assumptions`**: 8 categorized risks covering AWS ALB DNS setup, ElevenLabs credits, and OpenAI billing.
10. **`Scope Options`**: Operational scenario comparison (36h Standard Sprint vs. 48h Extended-Hour Sprint vs. 2-Engineer Parallel Sprint).
