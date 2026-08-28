# Razorpay Payment Recovery Agent — 5-Minute Pitch Script

> **Track:** Revenue Recovery (Razorpay AI Buildathon)  
> **Speaker Delivery Guide:** Timed for a 5-minute video demonstration.

---

### [0:00 – 0:30] 1. The Problem: Involuntary Churn & The ₹ Scale (30s)

*"Between 9% and 15% of all recurring subscription transactions fail on their first debit attempt. In India's booming ₹1.4 lakh crore subscription economy, over 40% of overall subscriber churn is not voluntary—it is caused by failed payments, expired cards, and transient banking glitches.*

*Traditional billing engines use 'dumb retries'—blindly hitting a card every 24 hours. This results in card network penalties, merchant chargeback risks, and annoyed customers. We built a Decline-Aware Recovery Agent that classifies failure reasons, applies hard compliance guardrails, and executes intelligent dunning actions with an immutable decision-to-outcome audit trail."*

---

### [0:30 – 2:30] 2. Live Dashboard & Exceptions Demo (2 min)

*(Screen Share: Live Executive Dashboard at `http://localhost:8000/dashboard`)*

*"Let's look at our live executive dashboard, running on real data captured from Razorpay test mode.*

*At the top, we see our key financial metrics:*
- ***Total At-Risk ARR:** ₹190,440.00 across 60 evaluated subscriptions.*
- ***Total ₹ Recovered:** ₹61,482.00.*
- ***Recovery Rate:** Exactly **32.28%**.*

*Notice that we do NOT claim an unrealistic 90% recovery rate. Why? Because we follow strict financial accounting: only automated soft decline retries that genuinely returned a successful debit are credited as recovered. Sending a nudge or having an email in flight is not counted as recovered revenue.*

*Looking at our **Decline Distribution Mix**:*
- ***50% Soft Declines:** 30 subscriptions with transient bank/insufficient fund errors. 18 were recovered via exponential backoff retries (1h, 6h, 24h); 12 hit our hard 3-attempt ceiling.*
- ***25% Hard Declines:** 15 subscriptions with expired cards or revoked mandates. 8 were nudged with self-serve links; 3 were held by Do-Not-Disturb hours; 2 were blocked by customer opt-out; 2 were blocked by our lifetime contact cap.*
- ***25% Risk Flags:** 15 subscriptions flagged for issuer risk or fraud check. Exactly 0 automated retries and 0 spam nudges were sent—all 15 were routed directly to human compliance operations.*

*Down below is our **Exceptions & Unresolved Cases Workbench**. This is what the agent could NOT resolve automatically. When we click 'Audit' on any subscription like `sub_soft_001`, a drill-down modal opens showing the complete decision-to-outcome timeline:*
- *Event capture $\rightarrow$ Decline classification $\rightarrow$ Policy reasoning $\rightarrow$ Real API retry execution $\rightarrow$ Succeeded debit.*

*Finally, in the **Query Inspector**, we expose the exact PostgREST SQL query and arithmetic proof behind every number on this screen."*

---

### [2:30 – 3:30] 3. Architecture & Immutable Audit Trail (1 min)

*(Screen Share: `ARCHITECTURE.md` System Flow Diagram)*

*"Under the hood, the architecture is built on three core tenets:*

1. ***Raw Webhook Ingestion & HMAC Verification:** Webhooks (`payment.failed`, `subscription.pending`, `subscription.halted`) are verified against raw request bytes and stored in an append-only table.*
2. ***Deterministic 3-Tier Policy Engine:** Maps failures into `SOFT_DECLINE`, `HARD_DECLINE`, and `RISK_FLAG`. It enforces strict exponential backoff, a hard 3-retry limit, and terminal stopping rules.*
3. ***Hard-Coded Compliance Guardrails:** DND hours (9:00 AM – 8:00 PM IST), customer opt-outs, and a 3-touch global lifetime cap are strictly hard-coded in Python, not left to LLM prompt judgment.*

*Every single action execution writes back into the **same row** in `recovery_audit_log`, ensuring one continuous decision-to-outcome audit trail."*

---

### [3:30 – 4:30] 4. The 'WHAT_BROKE' Story: Real Engineering Learnings (1 min)

*(Screen Share: `WHAT_BROKE.md` Entry 1)*

*"Let me share the most critical technical friction point we hit in Phase 1:*

*When verifying Razorpay's HMAC-SHA256 signatures, doing `json.dumps(payload)` in FastAPI failed intermittently. Why? Because standard JSON serializers alter whitespace separators, key order, and unicode escaping compared to the exact raw byte stream sent over the wire by Razorpay.*

*The fix: we now stream raw ASGI request bytes directly into the cryptographic verifier before any JSON parsing takes place. We documented all 12 real engineering edge cases—from DND IST timezone desynchronization to promise-to-pay check-in loops—in our public `WHAT_BROKE.md` log."*

---

### [4:30 – 5:00] 5. What We'd Build Next (30s)

*"If we had another sprint, we would expand in three areas:*
1. ***WhatsApp Interactive Recovery:** Delivering instant 1-click payment method updates via WhatsApp Interactive Messages with Razorpay Payment Links.*
2. ***UPI AutoPay Mandate Re-auth:** Automated fallback prompting customers to authorize UPI AutoPay when card recurring limits are reached.*
3. ***Predictive Retry Scheduling:** Machine learning to predict optimal debit times based on customer salary credit cycles.*

*Thank you for watching—our repo is open-source, fully tested with 41 passing automated tests, and ready for deployment."*
