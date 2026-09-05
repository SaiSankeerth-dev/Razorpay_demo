# Panel Preparation & 2-Minute Pitch — Razorpay AI Builder 2026

> **Target Track:** AI Revenue Recovery  
> **Audience:** Razorpay hiring managers, fintech system architects, and AI buildathon judges.

---

## ⏱️ Part 1: 2-Minute Video & Pitch Script

### [0:00 – 0:15] Problem & Measured Result (15s)
"Subscription businesses lose 9% to 15% of recurring revenue to involuntary payment failures. Conventional billing engines blindly hammer debit retries every 24 hours—burning retry limits on expired cards and risking card network penalties on fraud flags.

We built **RecoverX**. On our held-out 150-case benchmark, it achieves **37.59% recovery vs 28.19% baseline (+9.40pp absolute gain)** and **+3.78pp over rules alone**, recovering **+₹45,985.00 in incremental revenue**, eliminating **225 wasted retries**, and maintaining **strictly 0 risk violations**."

---

### [0:15 – 0:35] Architecture & Non-Negotiable Principle (20s)
"Our architecture follows one non-negotiable principle:
$$\text{AI Recommends} \longrightarrow \text{Deterministic Policy Firewall Authorizes} \longrightarrow \text{Financial Action Executes}$$

1. **Cryptographic Ingestion:** Validates HMAC-SHA256 signatures on raw request bytes and persists raw JSONB events.
2. **AI Diagnostician:** Semantically interprets ambiguous banking error descriptions, estimates empirical recovery probability $P(\text{recovery})$, recommends delay timing, and selects customer messaging strategies.
3. **Deterministic Policy Firewall:** An immutable Python guardrail layer that validates model recommendations against hard stopping rules, retry budgets (max 3), DND contact hours, and fraud quarantine rules **before any money moves or any message sends**."

---

### [0:35 – 1:00] Live Demo — Scenario 1: Successful Recovery (25s)
*(Screen share: CLI `python scripts/run_demo.py` or Live Dashboard)*
"In **Scenario 1**, a subscription fails due to a transient bank gateway timeout:
- The **AI Diagnostician** identifies root cause as `transient_banking_gateway_downtime`, predicts $P(\text{recovery}) = 0.88$, and recommends a 1-hour backoff retry.
- The **Policy Firewall** validates attempt #1 and authorizes `SCHEDULE_RETRY`.
- The **Action Executor** invokes Razorpay's test-mode API, the debit succeeds, and ₹2,499.00 in recurring revenue is recovered and logged in the continuous audit trail."

---

### [1:00 – 1:25] Live Demo — Scenario 2: Adversarial AI Containment (25s)
"What happens when an AI model hallucinates an unsafe action?
In **Scenario 2**, an incoming payment fails due to a `card_blacklisted` issuer decline.
- We inject an **adversarial AI recommendation** where the model hallucinates and recommends `SCHEDULE_RETRY`.
- The **Deterministic Policy Firewall** intercepts it immediately via rule `RULE_FIREWALL_RISK_QUARANTINE` and forces `ESCALATE_TO_HUMAN`.
- **Result:** Exactly **0 automated retry API calls** and **0 customer contact messages**. The case is safely quarantined in the human risk operations queue. **AI is never allowed to authorize money movement.**"

---

### [1:25 – 1:45] 3-Arm Benchmark Evidence (20s)
"Let's inspect our reproducible benchmark across 150 held-out evaluation scenarios (`python scripts/run_evaluation.py`):
- **vs Naive Baseline:** +₹45,985.00 incremental revenue recovered (+9.40pp lift), 225 wasted debit attempts eliminated.
- **vs Rules-Only:** +₹18,493.00 incremental revenue recovered (+3.78pp lift) through semantic understanding of unstructured gateway re-authentication errors.
- **Fintech Safety:** 114 illegal risk retries prevented (0.00% violation rate).
- **Model Quality:** 100.00% diagnosis accuracy, 100.00% intervention accuracy, 0 unsafe executions."

---

### [1:45 – 2:00] Closing Value Proposition (15s)
"RecoverX proves that AI in fintech is most powerful when paired with deterministic financial guardrails. It recovers 9.4pp more revenue, protects merchant risk scores, and respects customer compliance. Everything is 100% reproducible with `pytest -v` (60 passing tests). Thank you!"

---

## 🎯 Part 2: Comprehensive Technical Panel Q&A

### Category 1: AI & Machine Learning Architecture
**Q1: Why use AI here instead of purely deterministic rules?**  
> *Answer:* Rules excel at hard boundaries (e.g., "max 3 retries"). However, real-world payment failure context is messy: unstructured banking error descriptions (e.g. *"payment method requires re-authentication"*, *"issuer declined after additional verification"*), temporal failure history, customer value, and varying recovery likelihoods require semantic reasoning. The AI layer estimates empirical recovery probabilities and selects communication strategies; the Deterministic Policy Firewall authorizes every action before execution.

**Q2: What happens when AI is wrong?**  
> *Answer:* The Deterministic Policy Firewall sits between AI output and action execution. If AI recommends an unsafe action (e.g., retrying a blacklisted card or attempt #4 after budget exhaustion), the firewall intercepts and unconditionally overrides the action to `ESCALATE_TO_HUMAN` or `STOPPED_MAX_ATTEMPTS`.

**Q3: What happens if the AI model is unavailable, times out, or produces malformed JSON?**  
> *Answer:* All AI outputs are validated against strict Pydantic schemas (`AIDiagnosisResult`). If an external model times out, returns HTTP 500, or outputs invalid JSON, the engine automatically catches the exception and falls back to `LocalAIProvider`, which executes deterministic local diagnostics in <1ms with zero external network dependencies and zero cost.

**Q4: How is AI evaluated?**  
> *Answer:* Using a rigorous 3-arm held-out test benchmark (150 unseen scenarios, `seed=42`) comparing Naive Baseline vs Rules-Only vs AI+Policy Firewall. Ground truth is generated independently from scenario evidence, preventing circular evaluation or data leakage.

---

### Category 2: Fintech Safety, Webhooks & Compliance
**Q5: How do you prevent duplicate payment actions and ensure idempotency?**  
> *Answer:* Raw payloads are stored with unique `event_id` keys in `webhook_events`. Subscription state transitions are tracked in `subscription_recovery_state` and protected with thread-safe locks (`threading.RLock()`). Terminal subscriptions trigger `RULE_FIREWALL_TERMINAL_STOP` returning `NO_ACTION_ALREADY_STOPPED` without incrementing counters or double-debiting.

**Q6: How are webhooks secured?**  
> *Answer:* The webhook receiver validates Razorpay's HMAC-SHA256 signature directly on raw request bytes (`await request.body()`) before any JSON parsing. This prevents signature mismatches caused by JSON key re-ordering or whitespace serialization.

**Q7: How do retry limits and risk quarantine work?**  
> *Answer:* Hard retry ceiling is capped at strictly 3 attempts (`MAX_RETRY_BUDGET=3`). Attempt #4 transitions to terminal `STOPPED_MAX_ATTEMPTS`. For Tier-1 risk codes (`card_blacklisted`, `fraud_suspected`), `RULE_FIREWALL_RISK_QUARANTINE` guarantees strictly **0 retry API calls and 0 customer contacts**.

**Q8: How are customer preferences and Do-Not-Disturb (DND) hours enforced?**  
> *Answer:* Outbound communications are localized to `Asia/Kolkata` time. Messages generated outside 9:00 AM – 8:00 PM IST are held and rescheduled to 9:00 AM the next morning (`HOLD_DND`). Opted-out customers are permanently blocked (`BLOCKED_OPT_OUT`), and lifetime contact is capped at 3 total touches (`BLOCKED_LIFETIME_CAP`).

---

### Category 3: Business Impact & Accounting
**Q9: How much revenue is recovered and how is incremental revenue calculated?**  
> *Answer:* On 150 held-out scenarios (₹489,350 at risk), RecoverX recovers **₹183,940.00 (37.59%)**.  
> - Incremental revenue vs Naive Baseline: $\text{INR } 183,940.00 - \text{INR } 137,955.00 = \mathbf{+\text{INR } 45,985.00 \text{ (+9.40pp)}}$.  
> - Incremental revenue vs Rules-Only: $\text{INR } 183,940.00 - \text{INR } 165,447.00 = \mathbf{+\text{INR } 18,493.00 \text{ (+3.78pp)}}$.

**Q10: How did you eliminate 225 wasted retries?**  
> *Answer:* Naive retry blindly retried expired cards and revoked mandates 3 times each with a 0% recovery rate. RecoverX recognizes permanent hard declines immediately, blocks useless bank debits, and instead triggers self-serve payment update nudges.

---

### Category 4: Production Architecture & Scaling
**Q11: What is missing for production and how would you scale?**  
> *Answer:*  
> 1. **Storage:** Migrate local JSON store to PostgreSQL with connection pooling (PgBouncer) and row-level locking (`SELECT ... FOR UPDATE`).  
> 2. **Task Queue:** Add an asynchronous task queue (Celery / Redis Streams / AWS SQS) for scheduled retry dispatching.  
> 3. **Monitoring & Drift:** Deploy Prometheus metrics to track AI diagnostic latency, confidence calibration, and firewall override rates in real time. Model drift is detected by tracking distribution shifts in predicted $P(\text{recovery})$ vs actual bank settlement success rates.  
> 4. **Distributed Concurrency:** Use Redis distributed locks (`Redlock`) across multi-region webhook receivers.
