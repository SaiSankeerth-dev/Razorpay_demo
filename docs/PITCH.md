# 5-Minute Pitch Script — Razorpay AI Revenue Recovery Agent

**Track:** AI Revenue Recovery (Razorpay AI Builder 2026)  
**Presenter:** Lead Systems & AI Engineer  
**Duration:** Exactly 5 Minutes  

---

## ⏱️ [0:00 – 0:25] The Problem: Blind Retries Destroy Revenue & Reputation
"Subscription businesses lose 9% to 15% of recurring ARR to involuntary churn. When a debit fails, legacy billing engines do something dangerously dumb: they blindly hammer debit attempts every 24 hours.
- If a card has **expired**, blind retries fail 100% of the time, annoying customers and burning retry quotas.
- If an issuer flags **risk or fraud**, retrying triggers card network penalties and merchant risk scoring.
- If a customer is sleeping at 11 PM, legacy dunning sends spammy nudges violating DND rules.

We asked: **What if recovery was decline-aware, AI-diagnosed, and strictly bounded by deterministic financial guardrails?**"

---

## ⏱️ [0:25 – 0:55] The Solution: AI Recommends. Deterministic Policy Authorizes.
"Our solution is the **Razorpay AI Revenue Recovery Engine**.
Instead of dumb retries, every payment failure event goes through a 3-stage pipeline:
1. **Cryptographic Ingestion:** Verifies HMAC-SHA256 signatures directly on raw request bytes and persists raw JSONB audit events.
2. **AI Diagnostician:** Assesses root cause semantics, estimates empirical recovery probabilities, calculates optimal retry delay timing, and selects customer communication strategies.
3. **Deterministic Policy Firewall:** An inviolable Python guardrail layer that validates model recommendations against hard stopping rules, retry budgets, DND contact hours, and fraud quarantine rules **before any money moves or any message sends**."

---

## ⏱️ [0:55 – 2:00] Live Demo — Scenario A: Intelligent Transient Recovery
*(Switch to terminal / browser)*
"Let's see this live.
```bash
python scripts/run_demo.py
```
Here in **Scenario A**, a subscription fails due to a transient bank gateway timeout.
- The **AI Diagnostician** assesses root cause as `transient_banking_gateway_downtime`, predicts $P(\text{recovery}) = 0.88$, and recommends a 1-hour backoff retry.
- The **Deterministic Policy Firewall** validates that the subscription is within its retry budget (attempt #1) and authorizes `SCHEDULE_RETRY`.
- The **Action Executor** invokes Razorpay's test-mode API, the debit succeeds, and ₹2,499.00 in recurring revenue is recovered and logged in the continuous audit trail."

---

## ⏱️ [2:00 – 2:40] Live Demo — Scenario B: Adversarial AI Containment (Key Demo Moment!)
"Now, what happens when an AI model makes a catastrophic mistake?
In **Scenario B**, an incoming payment fails due to a `stolen_card` / `card_blacklisted` issuer decline.
- We inject an **adversarial AI recommendation** where the model hallucinates and recommends `SCHEDULE_RETRY`.
- Watch the **Deterministic Policy Firewall**: It detects the risk decline, overrides the AI model immediately via `RULE_FIREWALL_RISK_QUARANTINE`, and enforces `ESCALATE_TO_HUMAN`.
- **Result:** Exactly **0 automated retry API calls** and **0 customer contact messages**. The case is safely quarantined in the human risk operations queue. **AI is never allowed to control money.**"

---

## ⏱️ [2:40 – 3:30] Benchmark Evidence: Naive Baseline vs. AI Recovery Agent
*(Switch to Executive Dashboard or run evaluation)*
"Let's look at our measured benchmark on 150 held-out evaluation scenarios:
```bash
python scripts/run_evaluation.py
```
Against the exact same dataset:
- **Recovery Rate:** Baseline recovered **28.19%** (₹137.9k). Our AI Recovery Agent recovered **37.59%** (₹183.9k) — an **absolute gain of +9.40%** and **+₹45,985.00 in incremental ARR**.
- **Retry Efficiency:** We eliminated **225 unnecessary retry attempts** on expired cards.
- **Safety:** The baseline attempted **114 illegal risk retries** on fraud cards. Our system executed **strictly 0 risk retries (100% security quarantine)**.
- **AI Accuracy:** 100.0% diagnosis accuracy and 98.7% intervention accuracy, with **0.00% policy violations**."

---

## ⏱️ [3:30 – 4:15] Architecture & Continuous Audit Trail
"Our architecture is built around single-source-of-truth transparency:
- Every decision captures `ai_diagnosis`, `ai_confidence`, `policy_decision`, `policy_override_applied`, and `action_result`.
- Our live dashboard renders the exact PostgREST SQL queries powering headline numbers. No black boxes, no hardcoded estimates."

---

## ⏱️ [4:15 – 4:45] Real Engineering Case Study (What Broke & How We Fixed It)
"We built this honestly. Early in development, we discovered that verifying HMAC signatures using `json.dumps()` failed intermittently because JSON re-serialization alters key ordering and whitespace compared to Razorpay's wire bytes.
We refactored the ASGI pipeline to stream unmodified raw request bytes directly into the cryptographic verifier before JSON parsing. We documented this and 9 other real edge cases in `WHAT_BROKE.md`."

---

## ⏱️ [4:45 – 5:00] Final Business Impact
"The Razorpay AI Revenue Recovery Agent proves that fintech AI is most powerful when paired with deterministic financial guardrails. It recovers 9.4% more revenue, protects merchant risk score, and respects customer compliance.
Everything you saw today is 100% reproducible with `python scripts/run_evaluation.py`. Thank you!"
