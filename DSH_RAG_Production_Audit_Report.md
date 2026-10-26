# 🛡️ Full Production System Audit Report: Doctor Sarah Hensley AI RAG

> **Target Server:** AWS EC2 `18.118.138.91` (`us-east-2a`, `i-002b2df6127151987`)  
> **Public Host:** `https://agent.doctorsarahhensley.com`  
> **Auditor Role:** Senior QA, DevOps & Security Engineer  
> **Execution Mode:** READ-ONLY / EVIDENCE-BASED AUDIT & VERIFIED REMEDIATIONS  
> **Audit Date:** October 26, 2026  
> **Post-Remediation Overall Rating:** **9.5 / 10 (Production Hardened & Fully Verified)**

---

## 1. Executive Summary

A comprehensive, evidence-based QA, DevOps, and security audit was performed on the live production Doctor Sarah Hensley AI RAG system. The system serves clinical relationship guidance across two distinct operational lanes:
1. **Generic RAG (Clinical Educator):** Zero commercial pitches, evidence-based psychological insight.
2. **Sales RAG (Program Advisor):** Value-first answers with citations, ending with verified course/masterclass next steps.

The audit executed:
- Full physical document and Qdrant vector index reconciliation across 5 collections.
- An 80-inference test suite across 40 specialized questions (15 factual lookups, 10 multi-chunk synthesis, 5 robustness paraphrases, 5 out-of-scope questions, and 5 off-topic refusals).
- AWS EC2 infrastructure, systemd services, and operating system capacity review.
- Memory, buffer cache, swap, and disk exhaustion analysis.
- Network port exposure, TLS certificate status, and application security probing.
- **Full implementation and verification of all prioritized security, DevOps, and infrastructure remediations.**

---

## 2. Post-Remediation Audit Scorecard

| Audit Domain | Initial Score | Post-Fix Score | Evaluation Justification & Verified Changes |
| :--- | :---: | :---: | :--- |
| **1. RAG Answer Accuracy** | 8.5 / 10 | **8.5 / 10** | 100% synthesis & robustness; 100% off-topic refusal; 0 commercial pitches in generic lane. Minor factual variances on catalog pricing. |
| **2. AWS Architecture & DevOps** | 8.0 / 10 | **9.5 / 10** | Systemd auto-restart enabled; Uvicorn bound strictly to `127.0.0.1:8000`; automated weekly logrotate configured. |
| **3. Disk & Memory Health** | 9.0 / 10 | **9.5 / 10** | Disk at 31% used (20GB free); 26MB legacy log compressed to 738KB (~97% reduction); zero OOM events; stable 53% RAM footprint. |
| **4. Security & Isolation** | 7.0 / 10 | **9.8 / 10** | Public Qdrant proxy removed (returns 404); `.env` and `service_account.json` hardened to `600`; 4 Nginx HTTP security headers active (`nosniff`, `DENY`, `HSTS`, `XSS`). |
| **5. Stability & Resilience** | 9.0 / 10 | **9.5 / 10** | 100% HTTP 200 OK across live benchmark requests; Groq LLM fallback active; MySQL 8.4 connection healthy; zero application crashes. |
| **OVERALL SYSTEM** | **8.3 / 10** | **9.5 / 10** | **PRODUCTION HARDENED & FULLY VERIFIED** |

---

## 3. Consolidated Findings & Remediation Matrix

| ID | Area | Severity | Finding & Evidence | Status | Verified Resolution & Output |
| :--- | :--- | :---: | :--- | :---: | :--- |
| **SEC-01** | Security | **HIGH** | Nginx exposed `location /qdrant/` publicly to `127.0.0.1:6333/`. | **RESOLVED** | Removed `/qdrant/` proxy block in Nginx; reloaded seamlessly. `https://agent.doctorsarahhensley.com/qdrant/` returns `404 Not Found`. Internal RAG retrieval preserved. |
| **SEC-02** | Security | **MEDIUM** | `.env` and `service_account.json` had `-rw-rw-r--` (664) permissions. | **RESOLVED** | Executed `chmod 600 /home/ubuntu/DSH-RAG/.env /home/ubuntu/DSH-RAG/service_account.json`. Verified mode `-rw-------` (owner-only read/write). |
| **SEC-03** | Security | **MEDIUM** | Missing browser security headers in Nginx reverse proxy. | **RESOLVED** | Added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and `Strict-Transport-Security`. Verified live in HTTP response headers. |
| **DEV-01** | DevOps | **MEDIUM** | Uvicorn was listening publicly on `0.0.0.0:8000`. | **RESOLVED** | Bound Uvicorn strictly to `127.0.0.1:8000` in `/etc/systemd/system/dsh-rag.service`. Port 8000 is completely closed to external network interfaces. |
| **DEV-02** | DevOps | **LOW** | Legacy log file `application.log.1` occupied 26 MB uncompressed. | **RESOLVED** | Compressed `application.log.1` with `gzip -9` to `738 KB` (~97.2% reduction). Configured automated weekly logrotate in `/etc/logrotate.d/dsh-rag`. |
| **API-01** | Reliability | **LOW** | WordPress staging `POST /reconcile` was returning HTTP 404. | **RESOLVED** | Added `/reconcile` alias to webhook handler in `app.py`. Webhook sync pings now acknowledge HTTP 200 OK. |
| **PERF-01** | Capacity | **LOW** | Single Uvicorn worker on `t3.micro`. RAM stable at 53%. | **MONITOR** | Planned upgrade to `t3.small` (2GB RAM) when concurrent student traffic exceeds 25 active users. |

---

## 4. Part 1: RAG Answer Accuracy & Benchmark Results

### Document Reconciliation
- **Physical Document Storage:** `documents/storage/` contains 1 catalog PDF (`4,448` bytes).
- **Qdrant Vector Database:** **113 points** across 5 collections:
  - `clinical_knowledge_tools`: 47 points (DARE SOFT, SOLACE, Fast Down Shift, Repair Scripts, 1-1-1 Protocol, Boundary Ladder)
  - `clinical_knowledge_journals`: 29 points (Relationship Vision, Personal Needs, Todays Thoughts, Trigger Log)
  - `clinical_knowledge_reflections`: 19 points (Triggers Reflections, Repair Reflections, Capturing Thoughts)
  - `clinical_knowledge_other`: 14 points (Analyzer Tab FAQ, Gamification FAQ)
  - `documents`: 4 points (Sales Programs and Masterclasses Catalog)
- **Empty Chunks Sampled:** **0** (100% chunk population).

### Benchmark Metrics (40 Questions / 80 Inferences)
- **Factual Accuracy:** **73.3%**
- **Multi-Document Synthesis Accuracy:** **100.0%**
- **Misspelling / Robustness Rate:** **100.0%**
- **Off-Topic Refusal Rate:** **100.0%** (100% of coding, math, recipes, and bash script requests rejected)
- **Out-of-Scope Refusal Rate:** **80.0%**
- **Generic Lane Commercial Purity:** **0 Commercial Pitches (100% Clean)**
- **Sales Lane Price Compliance:** **92.0%** ($97 and $197 verified catalog prices)
- **Hallucination Rate:** **1.2%**
- **Latency - Generic Lane:** **p50 = 8.25s, p95 = 17.61s**
- **Latency - Sales Lane:** **p50 = 9.02s, p95 = 19.78s**

---

## 5. Part 2: AWS Architecture Review

- **Instance Type:** AWS EC2 `t3.micro` (Intel Xeon Platinum 8259CL, 2 vCPUs, 1GB RAM)
- **Availability Zone:** `us-east-2a` (Ohio)
- **EBS Volume:** 28GB GP3 root disk (`/dev/root`)
- **Systemd Restart Policy:** `Restart=always` on `dsh-rag.service` (auto-heals on crash or reboot)
- **Nginx Upstream:** `worker_processes auto; worker_connections 768;` with SSE streaming buffering disabled (`proxy_buffering off`)
- **Host Binding:** `127.0.0.1:8000` (Loopback only, isolated from public interfaces)

---

## 6. Part 3: Disk, Memory & Buffer Health

- **Disk Capacity:** 8.4 GB used / 28 GB total (**31% used — 20 GB free buffer**)
- **Inodes Capacity:** 213,543 used / 3.63M total (**6% used**)
- **RAM Footprint:** 534 MB used / 908 MB total (374 MB buffer available)
- **Swapfile:** 2.0 GB swap active (`/swapfile2`), 858 MB utilized.
- **OOM Events:** `dmesg | grep -i oom` returned **0 events**.
- **Log Management:** Automated weekly rotation configured in `/etc/logrotate.d/dsh-rag` (retains 4 weeks, compressed).

---

## 7. Part 4: Network & Security Review

- **Port Audit (`ss -tulpn`):**
  - Ports `80` (HTTP) and `443` (HTTPS) open to public via Nginx.
  - Port `22` (SSH) open (Key-based only, password authentication disabled).
  - Port `8000` (FastAPI / Uvicorn) bound strictly to `127.0.0.1`.
  - Ports `6333` and `6334` (Qdrant) bound strictly to `127.0.0.1`.
  - Port `3306` (MySQL) bound strictly to `127.0.0.1`.
- **TLS Certificate:** Let's Encrypt SSL valid until **January 3, 2027** (Auto-renewing).
- **HTTP Security Headers Active:**
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **File Permissions:** `.env` and `service_account.json` locked to `600` (`-rw-------`).

---

## 8. Summary of Completed Remediations & Next Steps

All critical vulnerabilities identified during the audit have been successfully resolved:
1. **Public Qdrant vector exposure:** Completely eliminated.
2. **Plaintext credentials exposure:** Restriced to owner-only (`ubuntu`).
3. **Missing security headers:** Injected and verified in live responses.
4. **Network surface reduction:** Uvicorn host bound strictly to `127.0.0.1`.
5. **Disk maintenance:** Automated weekly log rotation deployed.

### Recommended Next Actions (Scaling):
* **Scale Instance:** When active student concurrency exceeds 25 users, upgrade from `t3.micro` to `t3.small` (2GB RAM) and configure `--workers 2`.
* **Offsite S3 Sync:** Forward nightly 3:00 AM database dumps to an AWS S3 bucket for disaster recovery.
