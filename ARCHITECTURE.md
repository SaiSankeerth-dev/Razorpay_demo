# System Architecture — Decline-Aware Subscription Recovery Agent

> **Razorpay AI Buildathon (Revenue Recovery Track)**

---

## 1. End-to-End System Flow

```
[Razorpay Webhook Stream]
 (payment.failed / subscription.pending / subscription.halted)
            │
            ▼
 ┌────────────────────────┐
 │ Webhook Authenticator  │ ── HMAC-SHA256 Signature Verification on Raw Bytes
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Raw Webhook Ingestion  │ ── Persisted to `webhook_events` (Append-Only JSONB)
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Decline Classifier     │ ── Deterministic 3-Tier Error Taxonomy Mapping
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Policy Engine          │ ── Backoff Delays, Max 3 Retries, Stopping Rules
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Recovery Executors     │
 │ ├─ Soft Decline:       │ ── Test-Mode API Retry (Backoff: 1h, 6h, 24h)
 │ ├─ Hard Decline:       │ ── Customer Self-Serve Nudge (Email via SMTP)
 │ └─ Risk Flag:          │ ── Human Escalation Marker (0 Contact, 0 Retry)
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Compliance Guardrails  │ ── Hard-Coded DND (9am-8pm IST), Opt-Out & Lifetime Cap
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Continuous Audit Trail │ ── `recovery_audit_log` (Decision + Execution Outcome in Same Row)
 └────────────────────────┘
            │
            ▼
 ┌────────────────────────┐
 │ Live Next.js Dashboard │ ── Executive ARR Metrics, Exceptions Workbench & Drill-Down
 └────────────────────────┘
```

---

## 2. Audit Trail & State Database Schema

```sql
-- Single Continuous Decision-to-Outcome Audit Trail Table
CREATE TABLE public.recovery_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id VARCHAR(255),
    subscription_id VARCHAR(255) NOT NULL,
    payment_id VARCHAR(255),
    
    -- Phase 2 Decision Attributes
    decline_bucket VARCHAR(50) NOT NULL,            -- SOFT_DECLINE | HARD_DECLINE | RISK_FLAG
    reasoning TEXT NOT NULL,
    decided_action VARCHAR(50) NOT NULL,            -- SCHEDULE_RETRY | NUDGE_PAYMENT_UPDATE | ESCALATE_TO_HUMAN | NO_ACTION_ALREADY_STOPPED
    attempt_number INT NOT NULL DEFAULT 0,
    retry_delay_seconds INT,
    subscription_lifecycle_state VARCHAR(50) NOT NULL,
    
    -- Phase 3 Action Execution Attributes (Populated in Same Row)
    action_executed VARCHAR(50),                     -- RETRY_PAYMENT | SEND_EMAIL_NUDGE | ESCALATE_TO_HUMAN | HOLD_DND | BLOCKED_OPT_OUT | BLOCKED_LIFETIME_CAP
    action_result VARCHAR(50),                       -- SUCCESS | FAILED | SENT | FLAGGED_FOR_HUMAN_REVIEW | HELD_DND | BLOCKED
    action_details JSONB DEFAULT '{}'::jsonb,        -- Raw Razorpay API response or transport error
    executed_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Persistent Subscription Recovery State Machine
CREATE TABLE public.subscription_recovery_state (
    subscription_id VARCHAR(255) PRIMARY KEY,
    current_attempt_count INT DEFAULT 0 NOT NULL,
    status VARCHAR(50) NOT NULL,                    -- ACTIVE_RECOVERY | STOPPED_MAX_ATTEMPTS | ESCALATED_HUMAN_REVIEW | AWAITING_CUSTOMER_UPDATE | RESOLVED
    last_bucket VARCHAR(50),
    is_terminal BOOLEAN DEFAULT FALSE NOT NULL,
    total_contact_attempts INT DEFAULT 0 NOT NULL,   -- Global lifetime contact counter
    is_opted_out BOOLEAN DEFAULT FALSE NOT NULL,
    opted_out_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);
```

---

## 3. Why Decline-Aware Taxonomy Beats Fixed Retries

Traditional subscription billing engines treat all payment failures identically: they blindly hammer cards every 24 hours until hitting a hard cap. This damages merchant standing with card networks, incurs unnecessary decline fees, and triggers fraud scoring algorithms on cards that were simply stolen or expired. By mapping Razorpay's error taxonomy into three canonical buckets (**`SOFT_DECLINE`**, **`HARD_DECLINE`**, and **`RISK_FLAG`**), the agent only retries transient issues (`insufficient_funds`, gateway timeouts) with exponential backoff, halts retries on permanent failures (`expired_card`, `token_not_eligible`) to prompt immediate self-serve payment updates, and completely isolates risk declines (`payment_risk_check_failed`) for manual human review without sending a single spam message or unauthorized debit.

---

## 4. Why Compliance Guardrails Are Strictly Hard-Coded

In regulated financial environments governed by RBI recurring mandate rules and TRAI communication guidelines, non-negotiable legal invariants cannot be entrusted to non-deterministic LLM prompting. A model hallucination that fires a recovery notification at 2:00 AM or sends a 5th contact touch to an opted-out customer exposes the merchant to regulatory fines and consumer harassment complaints. Therefore, Do-Not-Disturb hours (9:00 AM – 8:00 PM IST), permanent customer opt-outs, and global lifetime contact caps ($N \le 3$) are hard-coded in Python as un-bypassable stateful guardrails. The LLM is reserved exclusively for natural language customer interactions and semantic intent parsing.
