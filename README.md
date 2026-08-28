# AI Revenue Recovery Agent for Razorpay Subscriptions

[![CI Test Suite](https://github.com/SaiSankeerth-dev/Razorpay_demo/actions/workflows/ci.yml/badge.svg)](https://github.com/SaiSankeerth-dev/Razorpay_demo/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)
[![Track: AI Revenue Recovery](https://img.shields.io/badge/Razorpay%20AI%20Builder-AI%20Revenue%20Recovery-blueviolet)](https://razorpay.com)

> **Failed subscription payments create involuntary churn.**  
> This system uses AI to diagnose payment failures and recommend the safest recovery intervention, while deterministic financial guardrails remain the final authority before any action executes.

---

## 📊 Benchmark Evidence (Held-Out Test Set)

Evaluated across **150 held-out subscription failure scenarios** comparing the AI Recovery Agent against legacy **Naive Fixed-Schedule Retry**:

| Metric | Naive Fixed Retry (Baseline) | AI Recovery Agent + Policy Firewall | Business Impact / Delta |
| :--- | :--- | :--- | :--- |
| **Recovery Rate (%)** | **28.19%** | **37.59%** | **+9.40% Absolute Gain** |
| **Revenue Recovered** | ₹137,955.00 | **₹183,940.00** | **+₹45,985.00 Incremental ARR** |
| **Retries Attempted** | 403 attempts | **178 attempts** | **225 Unnecessary Retries Eliminated** |
| **Risk / Fraud Retries** | 114 (Violations) | **0 (Zero Violations)** | **100% Fraud/Risk Isolation** |
| **Targeted Nudges** | 0 | **37 Nudges** | Self-serve credential recovery |
| **AI Diagnosis Accuracy** | N/A | **100.00%** | Root-cause semantic diagnosis |
| **AI Intervention Accuracy**| N/A | **98.67%** | Optimal intervention selection |
| **Policy Violation Rate** | 100% Risk Failures | **0.00%** | **Zero Unauthorized Money Movement** |

*All metrics are generated dynamically by `evaluation/benchmark.py` and reproducible via `python scripts/run_evaluation.py`.*

---

## 1. Problem
Subscription businesses lose 9%–15% of recurring ARR to involuntary payment failures. Conventional billing systems blindly retry debits every 24 hours:
- **Expired Cards:** Blind retries fail 100% of the time, burning retry limits and annoying cardholders.
- **Risk / Fraud Declines:** Retrying blacklisted cards incurs payment network decline fees and damages merchant risk scores.
- **Spammy Outreach:** Blind dunning ignores customer opt-outs and violates Do-Not-Disturb (DND) contact hours.

---

## 2. Solution: AI Recommends. Deterministic Policy Authorizes.
The **Razorpay AI Revenue Recovery Engine** replaces blind retries with an intelligent, decline-aware recovery pipeline:
1. **Cryptographic Webhook Ingestion:** Verifies HMAC-SHA256 signatures on raw request bytes and persists raw JSONB events.
2. **AI Diagnostician:** Assesses root cause semantics, estimates empirical recovery probability $P(\text{recovery})$, recommends delay timing (1h, 6h, 24h), and selects customer communication strategies.
3. **Deterministic Policy Firewall:** An immutable Python safety layer enforcing hard retry limits (max 3), fraud quarantine (0 contact, 0 retry), DND contact windows (9am–8pm IST), customer opt-outs, and lifetime contact caps.
4. **Action Executors:** Invokes Razorpay's Python SDK for test-mode debit retries, SMTP for self-serve payment link nudges, and risk operations routing.
5. **Continuous Audit Trail:** Records a single immutable audit row capturing AI diagnosis, policy authorization, override rationale, and financial outcome.

---

## 3. Architecture

```text
                    RAZORPAY TEST MODE / WEBHOOKS
                                 │
                                 ▼
                         WEBHOOK INGESTION
                    (HMAC-SHA256 Raw Request Bytes)
                                 │
                                 ▼
                        PAYMENT/USER CONTEXT
                                 │
                                 ▼
                          AI DIAGNOSTICIAN
                  (Root Cause, P(rec), Delay, Strategy)
                                 │
                                 ▼
                      STRUCTURED RECOMMENDATION
                     (Validated Pydantic Contract)
                                 │
                                 ▼
                     DETERMINISTIC POLICY FIREWALL
              (Risk Check, DND, Opt-Out, Cap, Retry Budget)
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
     APPROVE: RETRY       APPROVE: NUDGE       BLOCK: ESCALATE
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 ▼
                          ACTION EXECUTOR
                     (Razorpay SDK / SMTP Nudge)
                                 │
                                 ▼
                      CONTINUOUS AUDIT LEDGER
                                 │
                                 ▼
                         EVALUATION ENGINE
                    (Baseline vs AI Comparative)
```

---

## 4. AI Safety Model & Policy Firewall

```text
AI Recommendation ──> Schema Validation ──> Policy Firewall ──> Authorized Execution
                                                  │
                                            [Override Unsafe]
                                                  │
                                                  ▼
                                          ESCALATE_TO_HUMAN
```

| Guardrail Layer | Enforcement Mechanism | Safety Invariant Guaranteed |
| :--- | :--- | :--- |
| **Risk Quarantine** | Rule `RULE_FIREWALL_RISK_QUARANTINE` | If failure code relates to fraud or risk, AI retry/nudge recommendations are overridden to `ESCALATE_TO_HUMAN` (**0 retries, 0 contacts**). |
| **Retry Budget** | Rule `RULE_FIREWALL_MAX_RETRY_BUDGET_EXHAUSTED` | Subscriptions are capped at strictly **3 retries**. Attempt #4 transitions to terminal `STOPPED_MAX_ATTEMPTS`. |
| **Replay Idempotency** | Rule `RULE_FIREWALL_TERMINAL_STOP` | Subscriptions in terminal states ignore duplicate/replayed webhooks without re-triggering actions. |
| **Customer Opt-Out** | Rule `RULE_FIREWALL_OPT_OUT_GUARDRAIL` | Opted-out customers never receive automated outreach. |
| **Lifetime Contact Cap** | Rule `RULE_FIREWALL_LIFETIME_CAP_GUARDRAIL` | Monotonic global counter limits customer touches to 3 across the whole subscription lifecycle. |
| **DND Window Hours** | Rule `RULE_FIREWALL_DND_HOLD` | Nudges generated outside 9:00 AM – 8:00 PM IST are rescheduled to 9:00 AM next day. |

---

## 5. Quickstart & Setup

### Prerequisites
- Python 3.10+
- Git

### Installation
```bash
# Clone the repository
git clone https://github.com/SaiSankeerth-dev/Razorpay_demo.git
cd Razorpay_demo

# Create virtual environment
python -m venv venv
# Linux/macOS: source venv/bin/activate
# Windows: .\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

---

## 6. One-Command Evaluation & Demo

### 1. Run Benchmark Evaluation
```bash
python scripts/run_evaluation.py
```
*Evaluates Baseline vs AI Recovery Agent over 150 held-out scenarios and outputs `evaluation/results/benchmark.json` and `evaluation/results/benchmark.md`.*

### 2. Run 3-Minute Interactive Demo
```bash
python scripts/run_demo.py
```
*Demonstrates Scenario A (Transient Recovery), Scenario B (Adversarial AI Blocked by Policy), and Scenario C (Budget Exhaustion).*

### 3. Run Full Automated Test Suite (51 Tests)
```bash
pytest -v
```
*Executes unit, invariant, adversarial safety, compliance, and concurrency tests (100% passing).*

### 4. Launch Live Executive Dashboard
```bash
python -m uvicorn webhooks.server:app --host 0.0.0.0 --port 8000
```
Open **[http://localhost:8000/dashboard](http://localhost:8000/dashboard)** to view the live dashboard.

---

## 7. Documentation Index

- [`docs/CURRENT_STATE_AUDIT.md`](docs/CURRENT_STATE_AUDIT.md) — Pre-implementation repository audit & gap analysis.
- [`docs/AI_SAFETY_MODEL.md`](docs/AI_SAFETY_MODEL.md) — Formal specification of the Deterministic Policy Firewall.
- [`docs/EVALUATION.md`](docs/EVALUATION.md) — Dataset construction, partitioning, and mathematical evaluation formulas.
- [`docs/PITCH.md`](docs/PITCH.md) — Complete 5-minute presentation script.
- [`docs/PANEL_QA.md`](docs/PANEL_QA.md) — Comprehensive technical Q&A preparation.
- [`WHAT_BROKE.md`](WHAT_BROKE.md) — 10 engineering case studies detailing real bugs, root causes, and fixes.
- [`LIMITATIONS.md`](LIMITATIONS.md) — Honest boundaries of synthetic data, test mode, and local storage.

---

## 8. License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.
