# Razorpay Decline-Aware Subscription Payment Recovery Agent

> **Razorpay AI Buildathon — Revenue Recovery Track**  
> *Autonomous, decline-aware subscription recovery engine with deterministic policy guardrails, test-mode action execution, and a single continuous decision-to-outcome audit trail.*

---

## 📌 Executive Summary

Subscription businesses lose 9%–15% of recurring ARR to involuntary payment churn. Traditional billing systems blindly hammer debit attempts every 24 hours—annoying customers, triggering fraud scoring, and incurring network decline penalties.

This agent replaces dumb retries with **decline-aware intelligent recovery**:
1. **Cryptographic Webhook Ingestion (Phase 1):** Verifies HMAC-SHA256 signatures directly on raw request bytes and persists unmodified JSONB events.
2. **Deterministic 3-Tier Classifier & Policy Engine (Phase 2):** Maps Razorpay's error taxonomy into `SOFT_DECLINE`, `HARD_DECLINE`, and `RISK_FLAG`, applying exponential backoff (1h, 6h, 24h) with a hard 3-retry ceiling.
3. **Recovery Action Execution & Compliance Guardrails (Phase 3):** Dispatches real test-mode API retries, sends customer email update nudges, isolates risk declines (0 contact, 0 retry), tracks promise-to-pay commitments with exactly-once check-ins, and enforces non-negotiable compliance rules (DND 9am-8pm IST, opt-outs, 3-touch lifetime cap).
4. **Synthetic Batch Dataset & Live Dashboard (Phase 4):** Evaluates a realistic SaaS failure mix (60 subscriptions) and renders real-time ARR metrics, underlying SQL query proofs, and an honest Exceptions Workbench.

---

## 🏗️ Repository Architecture

```
Razorpay/
├── agent/                         # Core Recovery Intelligence & Compliance
│   ├── classifier.py              # 3-tier error taxonomy decline classifier
│   ├── policy_engine.py          # Deterministic policy rules & backoff scheduler
│   ├── decision_engine.py        # Webhook decision orchestrator
│   ├── compliance.py             # DND (9am-8pm IST), Opt-Out & Lifetime Cap Guardrails
│   ├── action_engine.py          # Phase 3 action execution dispatcher
│   ├── executors/                # Specific action executors
│   │   ├── retry_executor.py     # Razorpay test-mode API retry executor
│   │   ├── nudge_executor.py     # SMTP email nudge sender
│   │   ├── escalation_executor.py# Human escalation marker (0 contact, 0 retry)
│   │   └── promise_to_pay_executor.py # Exactly-once promise check-in tracker
│   └── models.py                 # Pydantic schemas & state enums
├── webhooks/                      # FastAPI Server & Cryptographic Verifiers
│   ├── server.py                 # Webhook receiver, dashboard APIs & HTML Dashboard UI
│   └── verifier.py               # Raw-bytes HMAC-SHA256 signature verifier
├── db/                            # Storage & Repository Layer
│   ├── client.py                 # Supabase client with in-memory offline fallback
│   ├── config.py                 # Environment configuration & compliance constants
│   ├── repository.py             # Continuous audit trail queries & state store
│   └── schema.sql                # Supabase PostgreSQL schema with RLS & indices
├── dashboard/                     # Next.js + Tailwind React Dashboard App
│   ├── app/                      # Next.js App Router (page.tsx, layout.tsx)
│   ├── lib/                      # Supabase client initializer
│   └── package.json              # Dashboard dependencies
├── scripts/                       # CLI Execution & Simulation Scripts
│   ├── generate_batch_data.py    # Generates 60 subscriptions through real pipeline
│   ├── verify_phase3.py          # Phase 3 acceptance runner
│   ├── verify_phase4.py          # Phase 4 acceptance runner
│   ├── simulate_webhook.py       # Webhook simulation runner
│   ├── simulate_customer_reply.py# CLI for Promise-to-Pay and Opt-Outs
│   └── create_plan_and_subscription.py # Razorpay SDK test plan provisioner
├── tests/                         # Comprehensive Pytest Suite (41 Tests)
│   ├── test_classifier.py
│   ├── test_policy_engine.py
│   ├── test_stopping_rules.py
│   ├── test_compliance_guardrails.py
│   ├── test_phase3_executors.py
│   ├── test_promise_to_pay.py
│   ├── test_batch_and_dashboard.py
│   ├── test_signature.py
│   └── test_webhooks.py
├── ARCHITECTURE.md                # System flow diagram & audit schema spec
├── WHAT_BROKE.md                  # 12 real engineering friction logs & learnings
├── PITCH_SCRIPT.md                # 5-minute video presentation guide
├── PANEL_PREP.md                  # 5 hardest Razorpay engineer interview Q&As
└── requirements.txt               # Backend Python dependencies
```

---

## 🚀 Quickstart & Setup Guide

### 1. Clone & Environment Setup
```bash
git clone https://github.com/your-username/razorpay-subscription-recovery.git
cd razorpay-subscription-recovery

# Create and activate Python virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate `.env` with your Razorpay Test Keys and Supabase credentials:
```ini
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
USE_LOCAL_DB=false
```
*(Note: If Supabase is offline or not configured, the agent seamlessly uses high-speed local persistence fallback).*

### 3. Run the Full Test Suite (41 Automated Tests)
```bash
pytest -v
```
*Expected: `41 passed in ~7s`.*

---

## 📊 Running the Live System & Dashboard

### 1. Run the Batch Dataset Pipeline (60 Subscriptions)
Generate 60 realistic subscription declines (50% Soft, 25% Risk, 25% Hard) and process them through the real recovery pipeline:
```bash
python scripts/generate_batch_data.py
```

### 2. Start the Backend & Executive Dashboard Server
```bash
uvicorn webhooks.server:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser to:
- **Interactive Executive Dashboard:** [`http://localhost:8000/dashboard`](http://localhost:8000/dashboard)
- **API Documentation (Swagger):** [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **Health Check:** [`http://localhost:8000/health`](http://localhost:8000/health)

---

## 🧪 Interactive CLI Utilities

### 1. Simulate a Customer Promise-to-Pay
```bash
python scripts/simulate_customer_reply.py promise sub_soft_001 2026-09-01 --notes "Customer committed to pay on salary credit"
```

### 2. Check in on a Promise-to-Pay (Strictly Exactly-Once)
```bash
# Check on date (fires check-in #1)
python scripts/simulate_customer_reply.py check-promise sub_soft_001 --date 2026-09-01

# Attempt second check-in (strictly blocked by guardrail)
python scripts/simulate_customer_reply.py check-promise sub_soft_001 --date 2026-09-02
```

### 3. Opt Out a Subscription from Outbound Notifications
```bash
python scripts/simulate_customer_reply.py opt-out sub_hard_002
```

---

## 🔒 Financial Safety & Compliance Invariants

| Guardrail | Enforcement Mechanism | Safety Guarantee |
| :--- | :--- | :--- |
| **Max 3 Retries** | Hard-coded counter in `subscription_recovery_state` | Attempt #4 is unconditionally blocked |
| **Risk Isolation** | Evaluated at Tier 1 before soft/hard logic | 0 automated contact sent, 0 retry API calls |
| **DND Window** | Localized to `Asia/Kolkata` (9:00 AM – 8:00 PM IST) | 11:00 PM nudges held & rescheduled to 9:00 AM |
| **Customer Opt-Out** | Stateful flag `is_opted_out = True` | Blocks all future nudges even on fresh declines |
| **Lifetime Contact Cap** | Global counter `total_contact_attempts` across life of sub | Blocks contact touch $N+1$ across all decline events |
| **Promise-to-Pay** | Monotonic `check_in_count` counter | Evaluates exactly ONCE; stops re-check loops |

---

## 📚 Documentation Directory
- [`ARCHITECTURE.md`](ARCHITECTURE.md): System architecture flow & audit trail schema.
- [`WHAT_BROKE.md`](WHAT_BROKE.md): 12 real engineering friction logs and learnings.
- [`PITCH_SCRIPT.md`](PITCH_SCRIPT.md): 5-minute video pitch presentation script.
- [`PANEL_PREP.md`](PANEL_PREP.md): 5 hardest technical questions & honest answers for judges.
