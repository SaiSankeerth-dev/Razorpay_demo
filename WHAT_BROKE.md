# What Broke — Razorpay Payment Recovery Agent Log

> **Submission Requirement:** A running engineering log of friction points, broken assumptions, edge cases, and unexpected behaviors discovered throughout development. Started in Phase 1 and updated continuously.

---

### Entry 1: Raw Bytes vs JSON Re-serialization in Webhook Signature Verification
* **What happened:** Attempting to verify webhook signatures using `json.dumps(payload)` inside request handlers failed intermittently because JSON serializers differ in key ordering, whitespace separators (`", "` vs `","`), and unicode escaping compared to the exact raw bytes transmitted over the wire by Razorpay.
* **Fix & Learning:** Always read raw request body bytes (`await request.body()`) directly from the ASGI/FastAPI stream before JSON parsing and pass those exact bytes / decoded UTF-8 string into `razorpay.utility.Utility.verify_webhook_signature`. Never re-serialize.

---

### Entry 2: Subscription State Machine Nuance (`created` vs `active` vs `pending` vs `halted`)
* **What happened:** Initial assumption was that a failed subscription creation triggers a failure event immediately. However, Razorpay's subscription state lifecycle explicitly requires authentication first:
  1. `created` → customer authorizes (eMandate / 3DS) → `authenticated` / `active`.
  2. Recurring billing auto-charge fails → moves to `pending` (retries active).
  3. Maximum automated retry attempts exhausted → moves to `halted` (manual customer retry required).
* **Fix & Learning:** Payment recovery agents must distinguish between `subscription.pending` (soft decline / retry window open) and `subscription.halted` (hard retry exhaustion requiring active customer intervention like payment method update).

---

### Entry 3: Supabase Payload Schema Polymorphism
* **What happened:** Webhook payloads differ significantly between `payment.failed` (root `payload.payment.entity` with `error_code`, `error_source`, `error_step`, `error_reason`) and `subscription.pending` / `subscription.halted` (root `payload.subscription.entity`).
* **Fix & Learning:** Implemented an append-only raw JSONB audit log table `webhook_events` in Supabase to capture the full raw JSON payload unmodified before downstream classification and recovery policies process it.
