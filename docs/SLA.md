# Service Level Agreement (SLA) & Operational Objectives (SLO)
**Application:** Doctor Sarah Hensley AI RAG (`DSH-RAG`)  
**Production Domain:** `https://agent.doctorsarahhensley.com/dsh-rag`  
**Effective Date:** October 2026  
**Document ID:** `SLA-DSH-PROD-2026`  
**Classification:** Production Service Level Agreement  

---

## 1. Executive Summary & Purpose
This document establishes the formal Service Level Agreement (SLA), Service Level Objectives (SLOs), and Service Level Indicators (SLIs) for the **Doctor Sarah Hensley AI Relationship Consultant & RAG Assistant**. 

This agreement governs service availability, performance latency, incident response times, maintenance windows, and disaster recovery commitments for production users.

---

## 2. Service Level Indicators (SLIs) & Objectives (SLOs)

### 2.1. Availability Commitment
The DSH-RAG service commits to a monthly availability target of **99.5%**:

$$\text{Availability} = \frac{\text{Total Minutes in Month} - \text{Unplanned Downtime Minutes}}{\text{Total Minutes in Month}} \times 100\%$$

| Metric | Target SLO | Allowable Error Budget / Month |
| :--- | :--- | :--- |
| **Monthly Uptime** | **&ge; 99.5%** | **&le; 3.65 hours** unplanned downtime |
| **Health Check Success Rate** | **&ge; 99.9%** | Evaluated via automated `/health` probes |
| **Crisis Guardrail Interception Rate** | **100.0%** | Zero tolerance for acute distress bypass |

---

### 2.2. Latency & Performance SLOs
Latency is measured from the receipt of the client request until the response begins streaming (Time to First Token) or completes transmission:

| Request Type | Target (p50) | Target (p95) | Target (p99) |
| :--- | :--- | :--- | :--- |
| **Semantic Cache Hit (Tier 1 & 2)** | &le; 20 ms | &le; 100 ms | &le; 250 ms |
| **Streaming RAG (Time-to-First-Token)** | &le; 1.2 s | &le; 1.8 s | &le; 3.0 s |
| **Full Consultative Response (End-to-End)** | &le; 2.8 s | &le; 4.5 s | &le; 7.0 s |
| **Document Ingestion (per PDF Page)** | &le; 0.5 s | &le; 1.5 s | &le; 3.0 s |

---

### 2.3. Disaster Recovery Objectives (RTO & RPO)

| Metric | Commitment | Mechanism |
| :--- | :--- | :--- |
| **RTO (Recovery Time Objective)** | **&le; 15 Minutes** | Automated SQLite hot backup swap & systemd restart |
| **RPO (Recovery Point Objective)** | **&le; 24 Hours** | Nightly automated SQLite online backup + S3 offsite replication |
| **Vector DB Restoration Time** | **&le; 30 Minutes** | Full parallel re-indexing from Google Drive source files |

---

## 3. Incident Severity Levels & Response Times

When an incident occurs, it is triaged into one of three severity tiers:

| Severity Level | Definition / Criteria | Acknowledgment Target | Target Resolution |
| :--- | :--- | :--- | :--- |
| **Sev-1: Critical** | Complete service outage; 5xx error rate > 10%; crisis safety guardrail failure. | **&le; 15 minutes** | **&le; 2 hours** |
| **Sev-2: Major** | High latency (p95 > 8s); Google Drive sync failure; WooCommerce customer sync failing. | **&le; 1 hour** | **&le; 6 hours** |
| **Sev-3: Minor** | Isolated cosmetic glitch; non-blocking dashboard warning; single-user cache miss. | **&le; 24 hours** | **&le; 3 business days** |

### Escalation Hierarchy:
1. **First Responder (On-Call Engineer)**: Investigates systemd logs, executes appropriate Runbook (`01_database_restore.md`, `02_credential_rotation.md`, or `03_drive_sync_recovery.md`).
2. **Technical Lead**: Engaged if Sev-1 is not stabilized within 30 minutes.
3. **Executive Stakeholder Notification**: Broadcast sent to Dr. Sarah Hensley operations team if Sev-1 exceeds 60 minutes.

---

## 4. Scheduled Maintenance & Change Management

1. **Standard Maintenance Window**: Sundays from **02:00 UTC to 04:00 UTC** (off-peak hours).
2. **Advance Notice**: Notice for user-impacting maintenance will be posted at least 48 hours in advance.
3. **Deployment Safety**: All production releases must be validated via GitHub Actions CI regression tests and deployed via the zero-downtime CD pipeline (`scripts/deploy_ec2.sh`).
4. **Emergency Patches**: Security hotfixes addressing critical CVEs or leaked credentials may be deployed immediately following Runbook 02 protocols.

---

## 5. Exclusions & Grace Periods
The following circumstances are excluded from monthly availability calculations:
* Client-side ISP or local network outages.
* Third-party foundational model outages (e.g. global Groq or OpenAI platform-wide outages documented on their official status pages).
* Pre-scheduled maintenance during authorized maintenance windows.
* Upstream Google Drive API quotas or domain-level DNS propagation delays beyond application control.

---

## 6. Document Governance & Review
This SLA is reviewed quarterly by the Lead DevOps Engineer and Product Operations. Any modifications to SLO targets require formal sign-off.
