# Razorpay Decline-Aware Subscription Payment Recovery Agent
### Razorpay AI Buildathon — Revenue Recovery Track (Phase 1: Research & Scaffold)

An intelligent agent system that monitors, ingests, and analyzes Razorpay subscription payment failures to recover lost recurring revenue.

---

## 📌 Executive Summary — Razorpay Research & Ground Truth

### 1. Razorpay Subscription State Machine
Subscriptions follow a strict deterministic lifecycle:
* **`created`**: Initial state when a subscription is provisioned; awaits customer authorization.
* **`authenticated`**: Customer has completed the first authentication/mandate authorization transaction (3DS/eMandate).
* **`active`**: Billing cycle is live; automated recurring charges are executed by Razorpay.
* **`pending`**: An automated recurring charge has failed; Razorpay enters automated retry phase.
* **`halted`**: All automated retry attempts have failed/exhausted; automatic charging is stopped and manual customer intervention (retry link or payment method update) is required.
* **`cancelled`**: Merchant or customer cancelled the subscription.
* **`completed`**: All scheduled billing cycles are finished.
* **`expired`**: Subscription expired without authorization.
* **`paused` / `resumed`**: Subscription temporarily suspended or restored.

### 2. Core Webhook Events Monitored
* **`payment.failed`**: Fired when a payment attempt fails. Contains detailed failure metadata (`error_code`, `error_description`, `error_source`, `error_step`, `error_reason`).
* **`subscription.pending`**: Fired when an active subscription transitions to `pending` due to a failed charge.
* **`subscription.halted`**: Fired when a subscription transitions to `halted` after exhausting retries.
* **`subscription.charged`**: Fired on successful subscription invoice charge.

### 3. Razorpay AI Playbook Summary (Foundation Section)
* **Layer 0 Setup Discipline**: Setup friction and infrastructure ergonomics must be solved at Layer 0 so that agent logic operates on robust harnesses and validated contracts.
* **Prompt × Context × Harness**: Agent systems require precise contextual schemas and deterministic harnesses (signature verification, typed DB models) rather than unconstrained prompting.
* **Fintech Guardrails**: Financial systems require immutable raw audit trails, constant-time cryptographic verification, and strict credential isolation (`.env` git-ignored).

---

## 🏗️ Repository Scaffold

```
Razorpay/
├── agent/                     # [Phase 2+] Agent classifier, LangGraph/CrewAI recovery policies
│   ├── __init__.py
│   └── README.md
├── webhooks/                  # FastAPI Webhook ingestion engine
│   ├── __init__.py
│   ├── server.py              # Webhook receiver routes & validation
│   └── verifier.py            # SDK-backed HMAC-SHA256 signature verification
├── db/                        # Supabase & database storage layer
│   ├── __init__.py
│   ├── client.py              # Supabase client initializer with test fallback
│   ├── config.py              # Pydantic environment configuration
│   ├── repository.py          # Raw webhook persistence & audit queries
│   └── schema.sql             # Supabase PostgreSQL schema with RLS & indices
├── scripts/                   # Provisioning and simulation CLI scripts
│   ├── create_plan_and_subscription.py # Creates Plan & Subscription via SDK
│   └── simulate_webhook.py    # Webhook simulation (tampered & valid payloads)
├── tests/                     # Comprehensive pytest test suite
│   ├── __init__.py
│   ├── test_signature.py      # Unit tests for signature verification/rejection
│   └── test_webhooks.py       # Integration tests for FastAPI endpoints & DB
├── .env.example               # Environment variables template
├── .gitignore                 # Strict secret and cache exclusions
├── requirements.txt           # Production dependencies
├── WHAT_BROKE.md              # Engineering friction & learnings log
└── README.md                  # System documentation & setup guide
```

---

## 🚀 Quickstart Guide

### Step 1: Environment Setup & Dependencies
```bash
# Clone the repository
git clone https://github.com/your-org/razorpay-subscription-recovery.git
cd razorpay-subscription-recovery

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate `.env` with your Razorpay Test Mode keys and Supabase credentials:
```ini
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_razorpay_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_supabase_anon_or_service_key
```

> **Security Note:** `.env` is strictly git-ignored. Never commit real API keys or secrets to version control.

### Step 3: Initialize Database Schema in Supabase
1. Open your **Supabase Dashboard** -> **SQL Editor**.
2. Copy the contents of `db/schema.sql` and run the script.
3. This creates the `webhook_events` table with UUID generation, JSONB indexes, and Row Level Security.

### Step 4: Start Webhook Receiver Server
```bash
uvicorn webhooks.server:app --host 0.0.0.0 --port 8000 --reload
```
* Server URL: `http://localhost:8000`
* Interactive API Docs: `http://localhost:8000/docs`
* Health Check: `http://localhost:8000/health`
* Webhook Ingest Endpoint: `http://localhost:8000/webhook`

---

## 🧪 Testing & Verification

### 1. Run Automated Test Suite
Run the full test suite verifying signature verification, tampered payload rejection, and database persistence:
```bash
pytest -v
```

### 2. Create Test Plan & Subscription in Razorpay Test Mode
Run the provisioning script using the official `razorpay-python` SDK:
```bash
python scripts/create_plan_and_subscription.py
```

### 3. Run Webhook Ingestion & Tampered Signature Rejection Simulation
Run the end-to-end simulation against the running server:
```bash
python scripts/simulate_webhook.py http://127.0.0.1:8000
```
This executes:
1. **Tampered Signature Test**: Sends altered signature $\rightarrow$ verifies server returns `HTTP 400 Bad Request`.
2. **`payment.failed` Test**: Sends valid HMAC signature $\rightarrow$ verifies `HTTP 200 OK` and raw DB logging.
3. **`subscription.pending` Test**: Sends valid HMAC signature $\rightarrow$ verifies `HTTP 200 OK` and raw DB logging.
4. **`subscription.halted` Test**: Sends valid HMAC signature $\rightarrow$ verifies `HTTP 200 OK` and raw DB logging.
5. **Database Audit**: Inspects captured raw records directly from the database.

---

## 🔒 Webhook Signature Verification Implementation

Webhook verification uses the official Razorpay SDK (`razorpay.utility.Utility.verify_webhook_signature`). Under the hood, this computes an HMAC-SHA256 digest over the exact raw body bytes:

$$\text{Signature} = \text{HMAC-SHA256}(\text{key} = \text{RAZORPAY\_WEBHOOK\_SECRET}, \text{msg} = \text{raw\_body\_bytes})$$

Constant-time comparison (`hmac.compare_digest`) prevents timing attacks, rejecting any tampered payload or mismatched secret.

---

## 📝 Phase 2 Roadmap
* [ ] Failure Classifier: Distinguish between Soft Declines (insufficient funds, temporary bank timeout), Hard Declines (expired card, invalid token), and Risk Flags.
* [ ] Policy Engine: Dynamic retry scheduling, smart dunning schedules, and customer communication channels.
* [ ] Agent Audit Trail: Transparent decision log for every automated recovery intervention.
