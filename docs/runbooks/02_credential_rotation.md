# Operational Runbook: Secret & Credential Rotation Procedures
**Document ID:** `RB-02-CRED-ROTATION`  
**Classification:** Operational Security Runbook  
**Target Application:** Doctor Sarah Hensley AI RAG (`DSH-RAG`)  
**Target Systems:** Groq, OpenAI, WordPress WooCommerce, Google Cloud Service Account, AWS EC2 SSH  
**Rotation Frequency:** Scheduled (every 90 days) OR Emergency (immediate upon suspected leak)  

---

## 1. Scope & Objective
This runbook defines the exact operational procedure for rotating all third-party API keys, system credentials, and authentication secrets used by the DSH-RAG application with **zero unplanned downtime**.

---

## 2. Inventory of System Secrets

| Secret Key / File | Service / Purpose | Impact if Compromised | Where Stored |
| :--- | :--- | :--- | :--- |
| `GROQ_API_KEY` | Groq Llama-3 LLM Generation | Unauthorized API usage / billing spikes | Host `.env` on EC2 |
| `OPENAI_API_KEY` | OpenAI Embeddings / Fallback | Billing spikes / quota exhaustion | Host `.env` on EC2 |
| `WP_CONSUMER_KEY` & `SECRET` | WooCommerce Customer Purchase Sync | Customer PII read / order data access | Host `.env` on EC2 |
| `service_account.json` | Google Drive Ingestion Access | Unauthorized access to internal clinical docs | Host root directory on EC2 |
| `EC2_SSH_KEY` | AWS EC2 Host Administration | Full server root/administrative compromise | GitHub Actions Secrets & `~/.ssh/` |
| `API_SECRET_KEY` | DSH-RAG Internal Webhook Auth | Unauthorized ingestion / cache bypass | Host `.env` on EC2 |

---

## 3. Step-by-Step Rotation Procedures

### 3.1. Groq API Key Rotation (`GROQ_API_KEY`)
1. Log into the [Groq Console](https://console.groq.com/keys).
2. Click **Create API Key**, name it `dsh-rag-prod-<YYYYMMDD>`, and copy the new token (`gsk_...`).
3. SSH into the AWS EC2 production server:
   ```bash
   ssh -i C:\Tools\python-qdrant-server.pem ubuntu@18.118.138.91
   ```
4. Open the environment file and update the key:
   ```bash
   sed -i 's/^GROQ_API_KEY=.*/GROQ_API_KEY=gsk_NEW_KEY_HERE/' /home/ubuntu/DSH-RAG/.env
   ```
5. Restart the service to load the new key:
   ```bash
   sudo systemctl restart dsh-rag
   ```
6. Verify live LLM inference with a test prompt:
   ```bash
   curl -s -X POST http://127.0.0.1:8000/query \
     -H "Content-Type: application/json" \
     -d '{"query": "Hello Dr Sarah", "user_id": "test_rot"}' | grep -o '"answer"'
   ```
7. Return to the Groq Console and **Revoke/Delete** the old API key.

---

### 3.2. OpenAI API Key Rotation (`OPENAI_API_KEY`)
1. Log into [OpenAI Platform API Keys](https://platform.openai.com/api-keys).
2. Create a restricted key named `dsh-rag-embeddings-<YYYYMMDD>` (Permissions: `Model inference`).
3. Update the `.env` on the EC2 host:
   ```bash
   sed -i 's/^OPENAI_API_KEY=.*/OPENAI_API_KEY=sk-proj-NEW_KEY_HERE/' /home/ubuntu/DSH-RAG/.env
   sudo systemctl restart dsh-rag
   ```
4. Test embedding generation:
   ```bash
   python3 -c "from src.embeddings import get_embeddings; print('Embeddings OK:', len(get_embeddings('test')) > 0)"
   ```
5. In OpenAI dashboard, delete the old key after confirming 5 minutes of clean logs.

---

### 3.3. WordPress WooCommerce REST API Credentials
1. Log into Dr. Sarah's WordPress WP-Admin: `https://doctorsarahhensley.com/wp-admin`.
2. Navigate to **WooCommerce &rarr; Settings &rarr; Advanced &rarr; REST API**.
3. Click **Add key**:
   * Description: `DSH-RAG Production Sync <YYYYMMDD>`
   * User: Authorized Administrator
   * Permissions: `Read` (Write is NOT required for customer habit sync)
4. Generate and copy the **Consumer Key** (`ck_...`) and **Consumer Secret** (`cs_...`).
5. Update on EC2 host `.env`:
   ```bash
   sed -i 's/^WP_CONSUMER_KEY=.*/WP_CONSUMER_KEY=ck_NEW_KEY/' /home/ubuntu/DSH-RAG/.env
   sed -i 's/^WP_CONSUMER_SECRET=.*/WP_CONSUMER_SECRET=cs_NEW_SECRET/' /home/ubuntu/DSH-RAG/.env
   sudo systemctl restart dsh-rag
   ```
6. Test customer purchase record fetching:
   ```bash
   python3 -c "
   from src.user_db import UserDatabase
   u = UserDatabase('users_data.db')
   print('WooCommerce Sync:', u.sync_woocommerce_purchases('test@example.com'))
   "
   ```
7. Revoke the old REST API key in WooCommerce settings.

---

### 3.4. Google Cloud Service Account Key (`service_account.json`)
1. Open the [Google Cloud IAM Console](https://console.cloud.google.com/iam-admin/serviceaccounts).
2. Select project containing the Google Drive API integration.
3. Select the active service account &rarr; **Keys** tab &rarr; **Add Key &rarr; Create new key (JSON)**.
4. Download the newly generated JSON key file to your secure local machine.
5. Securely transfer the new key file to the EC2 host:
   ```bash
   scp -i C:\Tools\python-qdrant-server.pem new_service_account.json ubuntu@18.118.138.91:/home/ubuntu/DSH-RAG/service_account.json.new
   ```
6. On the EC2 host:
   ```bash
   chmod 600 /home/ubuntu/DSH-RAG/service_account.json.new
   mv /home/ubuntu/DSH-RAG/service_account.json.new /home/ubuntu/DSH-RAG/service_account.json
   sudo systemctl restart dsh-rag
   ```
7. Test Google Drive folder query:
   ```bash
   python3 -c "from src.drive_service import DriveService; d = DriveService(); print('Drive Connected:', d.test_connection())"
   ```
8. In Google Cloud Console, **Delete** the old service account key ID.

---

### 3.5. AWS EC2 SSH Key Pair Rotation
1. Generate a new high-security ED25519 or RSA-4096 key pair locally:
   ```bash
   ssh-keygen -t ed25519 -C "dsh-rag-admin-2026" -f ./dsh-rag-ec2-new.pem
   ```
2. Copy the public key content (`dsh-rag-ec2-new.pem.pub`).
3. SSH into the server using the **current** key:
   ```bash
   ssh -i C:\Tools\python-qdrant-server.pem ubuntu@18.118.138.91
   ```
4. Append the new public key to `~/.ssh/authorized_keys`:
   ```bash
   echo "ssh-ed25519 AAAAC3... dsh-rag-admin-2026" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```
5. **DO NOT CLOSE YOUR CURRENT TERMINAL**. Open a second terminal and verify login with the new key:
   ```bash
   ssh -i ./dsh-rag-ec2-new.pem ubuntu@18.118.138.91 "echo 'New SSH key login SUCCESSFUL'"
   ```
6. Update the GitHub Actions Secret:
   * Go to `https://github.com/devqastoretrans-qa/DSH-RAG/settings/secrets/actions`.
   * Update `EC2_SSH_KEY` with the full private key content of `./dsh-rag-ec2-new.pem`.
7. Once verified, remove the old public key line from `~/.ssh/authorized_keys` on EC2.

---

## 4. Emergency Revocation Protocol (Active Breach)
If an API key is committed to a public repository or detected in logs:
1. **Immediate Revocation**: Go directly to the provider console and delete the compromised token immediately.
2. **Issue New Key**: Follow the step-by-step procedure above to provision and apply a replacement.
3. **Audit Access Logs**: Check Groq / OpenAI / CloudWatch usage graphs for unexpected spikes during the exposure window.
4. **Git Purge**: If committed to Git, use `git filter-repo` or BFG Repo-Cleaner to completely expunge the commit from history, then rotate GitHub Personal Access Tokens.
