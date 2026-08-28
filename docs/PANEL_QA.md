# Panel Preparation Q&A — Razorpay AI Builder 2026

Expert technical and architectural answers for hackathon judges, fintech engineers, and executive reviewers.

---

## 🧠 Category 1: AI & Machine Learning Architecture

### Q1: Why use AI here? Why not just use deterministic rules for everything?
> **Answer:**  
> Deterministic rules excel at hard boundaries (e.g., "never retry more than 3 times" or "never retry a blacklisted card"). However, payment failure context is nuanced: error descriptions from global banking gateways contain varied, unstructured text descriptions, customer retry history, transaction timing, and varying recovery likelihoods.  
> The AI layer provides **judgment**: evaluating failure semantics, estimating empirical recovery probabilities ($P(\text{recovery})$), recommending optimal backoff intervals, and selecting customer communication strategies. Crucially, we place deterministic rules *after* AI to validate and authorize every recommendation.

### Q2: What happens if the AI hallucinates or outputs an unsafe recommendation?
> **Answer:**  
> The **Deterministic Policy Firewall** (`agent/policy_firewall.py`) intercepts the AI output before any action is dispatched. If the AI hallucinates a `SCHEDULE_RETRY` on a risk decline, attempt #4, or an expired card, the firewall unconditionally overrides the action to `ESCALATE_TO_HUMAN` or `NO_ACTION_ALREADY_STOPPED` and logs the override rationale in the audit trail. AI has zero direct access to debit APIs.

### Q3: How is the AI evaluated, and how do you handle malformed JSON outputs?
> **Answer:**  
> 1. We evaluate the AI on failure diagnosis accuracy (100.0%) and intervention accuracy (98.7%) across a held-out dataset of 150 scenarios (`python scripts/run_evaluation.py`).  
> 2. All model outputs are strictly parsed into validated Pydantic domain models (`AIDiagnosisResult`). If a model produces invalid JSON or unknown action tokens, the schema validator catches the exception and engages a safe fallback with 0 unauthorized financial execution.

---

## 💳 Category 2: Fintech, Risk & Compliance

### Q4: How do you guarantee that a fraud or risk decline is never retried?
> **Answer:**  
> Through a two-layer guarantee:
> 1. The 3-tier decline classifier maps risk-related error codes (`card_blacklisted`, `fraud_suspected`, `stolen_card`) to `RISK_FLAG`.
> 2. Rule `RULE_FIREWALL_RISK_QUARANTINE` in the Policy Firewall overrides any automated retry or nudge recommendation to `ESCALATE_TO_HUMAN`, guaranteeing **strictly 0 automated retries and 0 automated customer contacts**.

### Q5: How do you handle duplicate webhooks and prevent double debits?
> **Answer:**  
> 1. Raw webhooks are recorded in an append-only ledger (`webhook_events`).  
> 2. Subscription state is tracked in `subscription_recovery_state` with thread-safe locks (`threading.RLock()`).  
> 3. Once a subscription reaches terminal state (`STOPPED_MAX_ATTEMPTS` or `ESCALATED_HUMAN_REVIEW`), subsequent duplicate or replayed webhooks trigger `RULE_FIREWALL_TERMINAL_STOP` and return `NO_ACTION_ALREADY_STOPPED`, making repeated webhooks completely idempotent.

### Q6: How do compliance guardrails handle customer contact hours?
> **Answer:**  
> Nudge communications are checked against local `Asia/Kolkata` time. Outbound nudges generated outside 9:00 AM – 8:00 PM IST are held and rescheduled to 9:00 AM the next morning (`HOLD_DND`). Furthermore, opt-outs permanently block outreach, and a monotonic lifetime counter caps contact at 3 total touches across the subscription lifetime.

---

## 📈 Category 3: Financial Metrics & Business ROI

### Q7: What is your baseline, and how is incremental revenue calculated?
> **Answer:**  
> The baseline is **Naive Fixed-Schedule Retry** (blind 24-hour retries up to 3 attempts with 0 decline awareness and 0 customer nudging).  
> In our held-out test evaluation:
> - Baseline recovered **₹137,955.00** (28.19% recovery rate).
> - AI Recovery Agent recovered **₹183,940.00** (37.59% recovery rate).
> - Incremental Recovered Revenue is **+₹45,985.00 (+9.40% absolute gain)**.
> All metrics are generated dynamically by `evaluation/benchmark.py`.

### Q8: How did you eliminate 225 unnecessary retries?
> **Answer:**  
> Naive retry blindly retried expired cards and revoked mandates 3 times each (wasting 3 attempts $\times$ failures = 0% success). Our agent recognizes permanent hard declines immediately, blocks useless bank debits, and instead triggers self-serve payment update nudges.

---

## 🚀 Category 4: Production Readiness & Scale

### Q9: What architectural changes would you make before deploying to millions of subscriptions?
> **Answer:**  
> 1. Transition the local file store to distributed PostgreSQL with connection pooling (PgBouncer) and row-level locking (`SELECT ... FOR UPDATE`).  
> 2. Add an asynchronous task queue (Celery / Redis / AWS SQS) for scheduled retry dispatching.  
> 3. Implement merchant-level configurable compliance rules per country/jurisdiction.  
> 4. Deploy Prometheus metrics to monitor AI diagnostic latency, confidence calibration, and firewall override rates in real time.
