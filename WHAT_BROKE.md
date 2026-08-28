# What Broke — Razorpay Payment Recovery Agent Log

> **Submission Requirement:** A running engineering log of friction points, broken assumptions, edge cases, and unexpected behaviors discovered throughout development. Started in Phase 1 and updated continuously.

---

### Entry 1: Raw Bytes vs JSON Re-serialization in Webhook Signature Verification (Phase 1)
* **What happened:** Attempting to verify webhook signatures using `json.dumps(payload)` inside request handlers failed intermittently because JSON serializers differ in key ordering, whitespace separators (`", "` vs `","`), and unicode escaping compared to the exact raw bytes transmitted over the wire by Razorpay.
* **Fix & Learning:** Always read raw request body bytes (`await request.body()`) directly from the ASGI/FastAPI stream before JSON parsing and pass those exact bytes / decoded UTF-8 string into `razorpay.utility.Utility.verify_webhook_signature`. Never re-serialize.

---

### Entry 2: Subscription State Machine Nuance (`created` vs `active` vs `pending` vs `halted`) (Phase 1)
* **What happened:** Initial assumption was that a failed subscription creation triggers a failure event immediately. However, Razorpay's subscription state lifecycle explicitly requires authentication first:
  1. `created` → customer authorizes (eMandate / 3DS) → `authenticated` / `active`.
  2. Recurring billing auto-charge fails → moves to `pending` (retries active).
  3. Maximum automated retry attempts exhausted → moves to `halted` (manual customer retry required).
* **Fix & Learning:** Payment recovery agents must distinguish between `subscription.pending` (soft decline / retry window open) and `subscription.halted` (hard retry exhaustion requiring active customer intervention like payment method update).

---

### Entry 3: Supabase Payload Schema Polymorphism (Phase 1)
* **What happened:** Webhook payloads differ significantly between `payment.failed` (root `payload.payment.entity` with `error_code`, `error_source`, `error_step`, `error_reason`) and `subscription.pending` / `subscription.halted` (root `payload.subscription.entity`).
* **Fix & Learning:** Implemented an append-only raw JSONB audit log table `webhook_events` in Supabase to capture the full raw JSON payload unmodified before downstream classification and recovery policies process it.

---

### Entry 4: Ambiguous Razorpay Error Codes & Taxonomy Precedence (Phase 2)
* **What happened:** In real Razorpay webhook payloads, certain bank declines return generic `BAD_REQUEST_ERROR` with `error_reason = "payment_failed"` without a granular sub-code, while others provide descriptive text in `error_description` (e.g. "Card has expired (expiry date 05/24 in past)"). A naive regex or string match on reason alone would misclassify expired cards as generic payment failures.
* **Fix & Learning:** Established a deterministic 3-tier classification hierarchy:
  1. **Tier 1 (Risk / Fraud):** Evaluates security filters first (`payment_risk_check_failed`, blacklisted card, issuer security blocks).
  2. **Tier 2 (Hard Decline):** Evaluates permanent credential issues (`expired_card`, `token_not_eligible`, mandate revoked, `subscription.halted`).
  3. **Tier 3 (Soft Decline):** Evaluates transient bank/gateway errors (`insufficient_funds`, network timeout, `subscription.pending`).
  Any ambiguous generic failure is defaulted to `SOFT_DECLINE` with low risk to prevent permanent premature lockouts while remaining safely bounded by the max retry limit.

---

### Entry 5: Replay Webhook Storms & Terminal State Invariants (Phase 2)
* **What happened:** When payment recovery retries are exhausted (attempt #3 reached), subsequent replayed webhooks (caused by Razorpay's automated delivery retry if a merchant server takes > 5s) could trigger race conditions, re-queue duplicate retries, or inflate attempt counters past the safety boundary.
* **Fix & Learning:** Implemented a persistent `subscription_recovery_state` table with an immutable `is_terminal` flag. When a subscription enters `STOPPED_MAX_ATTEMPTS` or `ESCALATED_HUMAN_REVIEW`, all future webhook evaluations return `NO_ACTION_ALREADY_STOPPED` without incrementing attempt numbers, providing strict idempotency.

---

### Entry 6: Hard-Coded Policy Boundaries vs LLM Judgment (Phase 2)
* **What happened:** Debating whether to let an LLM agent determine retry backoff and escalation rules per case.
* **Fix & Learning:** Regulated payment recovery requires strict financial invariants (e.g., RBI recurring mandate retry guidelines and card network debit frequencies). Non-deterministic LLM reasoning cannot guarantee that attempt #4 is never scheduled or that a stolen card is never retried. Therefore, policy execution and stopping rules are strictly hard-coded in Python as non-negotiable safety guardrails; LLMs are reserved for semantic reasoning and communications in Phase 3+.
