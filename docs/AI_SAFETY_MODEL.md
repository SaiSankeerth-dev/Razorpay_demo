# AI Safety & Policy Firewall Model

> **Core System Invariant:**  
> **AI Diagnostician Recommends $\longrightarrow$ Deterministic Policy Firewall Authorizes $\longrightarrow$ Financial Action Executes.**

---

## 1. Architectural Safety Boundary

In financial recovery systems, allowing an unconstrained Large Language Model or autonomous agent to directly invoke debit APIs or customer communications creates unacceptable risks:
- Hallucinated or runaway retries violating payment scheme rules (RBI recurring mandate guidelines, Visa/Mastercard retry velocity caps).
- Unauthorized debit attempts on reported stolen or blacklisted cards triggering regulatory penalties and fraud scoring.
- Customer harassment violating DND hours or ignoring explicit opt-out requests.

To eliminate these failure modes, this architecture places an **immutable, hard-coded Deterministic Policy Firewall** between model recommendations and execution:

`	ext
               ┌───────────────────────────────────────────────────────────┐
               │                 RAZORPAY PAYMENT FAILURE                  │
               └─────────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
               ┌───────────────────────────────────────────────────────────┐
               │             CRYPTOGRAPHIC WEBHOOK VERIFICATION            │
               │               (HMAC-SHA256 Raw Request Bytes)             │
               └─────────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
               ┌───────────────────────────────────────────────────────────┐
               │              AI DIAGNOSTICIAN (JUDGMENT LAYER)             │
               │   • Predicts Root Cause & Empirical Recovery Probability  │
               │   • Formulates Recommended Action & Delay Hours           │
               │   • Selects Customer Messaging Strategy & Confidence      │
               └─────────────────────────────┬─────────────────────────────┘
                                             │
                                             │ Structured Recommendation
                                             ▼
               ═════════════════════════════════════════════════════════════
               █████████████ DETERMINISTIC POLICY FIREWALL █████████████████
               ═════════════════════════════════════════════════════════════
               │ 1. Schema Validation (Pydantic contract)                  │
               │ 2. Risk Quarantine Check (Zero outreach, zero retry)      │
               │ 3. Stopping Rules & Terminal State Replay Blocker        │
               │ 4. Retry Budget Ceiling Check (Hard max 3 attempts)       │
               │ 5. Customer Opt-Out Compliance Check                      │
               │ 6. Lifetime Contact Touch Limit Check (Max 3 contacts)    │
               │ 7. Do-Not-Disturb (DND) Contact Hours (9am-8pm IST)       │
               │ 8. Hard Decline Debit Prevention                          │
               ═════════════════════════════════════════════════════════════
                                             │
                       ┌─────────────────────┼─────────────────────┐
                       │                     │                     │
                       ▼                     ▼                     ▼
               ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
               │   AUTHORIZED  │     │   AUTHORIZED  │     │    BLOCKED    │
               │  DEBIT RETRY  │     │  EMAIL NUDGE  │     │ RISK ISOLATE  │
               │  (Phase 3 SDK)│     │  (Phase 3 SMTP│     │ (0 Contact)   │
               └───────┬───────┘     └───────┬───────┘     └───────┬───────┘
                       │                     │                     │
                       └─────────────────────┼─────────────────────┘
                                             ▼
               ┌───────────────────────────────────────────────────────────┐
               │                 CONTINUOUS AUDIT LEDGER                   │
               │  (Records AI Diagnosis, Policy Decision, Overrides & ROI) │
               └───────────────────────────────────────────────────────────┘
`

---

## 2. Inviolable Policy Firewall Invariants

| Guardrail Layer | Enforcement Mechanism | Safety Invariant Guaranteed |
| :--- | :--- | :--- |
| **1. Risk Quarantine** | Rule RULE_FIREWALL_RISK_QUARANTINE | If failure code relates to fraud, issuer risk, or blacklisted instruments, AI recommendations are overridden to ESCALATE_TO_HUMAN. **Zero retry API calls and zero automated customer contacts.** |
| **2. Max Retry Budget** | Rule RULE_FIREWALL_MAX_RETRY_BUDGET_EXHAUSTED | Subscriptions are capped at strictly **3 retry attempts**. Attempt #4 is unconditionally blocked and the subscription transitions to terminal STOPPED_MAX_ATTEMPTS. |
| **3. Replay Idempotency** | Rule RULE_FIREWALL_TERMINAL_STOP | Subscriptions in terminal states (STOPPED_MAX_ATTEMPTS, ESCALATED_HUMAN_REVIEW) ignore replayed or out-of-order webhooks. Replays cannot reopen automation. |
| **4. Customer Opt-Out** | Rule RULE_FIREWALL_OPT_OUT_GUARDRAIL | If is_opted_out = True, all outbound customer nudges are permanently blocked, even upon fresh subsequent payment declines. |
| **5. Lifetime Touch Cap** | Rule RULE_FIREWALL_LIFETIME_CAP_GUARDRAIL | Monotonic global counter 	otal_contact_attempts limits lifetime customer contacts to **3 touches**. Contact +1$ is strictly blocked across all decline cycles. |
| **6. DND Window Hours** | Rule RULE_FIREWALL_DND_HOLD | Localized to Asia/Kolkata (9:00 AM – 8:00 PM IST). Any nudge generated between 8:00 PM and 9:00 AM is held and rescheduled to 9:00 AM the next morning. |
| **7. Hard Decline Protection**| Rule RULE_FIREWALL_HARD_DECLINE_NUDGE_ONLY | Permanent credential invalidations (expired cards, deleted tokens, revoked mandates) can never be debited via auto-retry; AI retry recommendations are forced to customer nudges. |

---

## 3. Adversarial Containment Matrix

The table below demonstrates how the Deterministic Policy Firewall intercepts and neutralizes adversarial, hallucinated, or malformed AI outputs:

| Scenario | Raw AI Recommendation | Deterministic Policy Firewall Action | Final Authorized Execution | Audit Outcome Logged |
| :--- | :--- | :--- | :--- | :--- |
| **Adversarial Risk Prompt** | SCHEDULE_RETRY on stolen_card | **BLOCKED** via RULE_FIREWALL_RISK_QUARANTINE | ESCALATE_TO_HUMAN | Override: True (Security Quarantine) |
| **Opted-Out Customer** | NUDGE_PAYMENT_UPDATE on opted-out sub | **BLOCKED** via RULE_FIREWALL_OPT_OUT_GUARDRAIL | NO_ACTION_ALREADY_STOPPED | Override: True (Opt-out enforced) |
| **Exhausted Budget** | SCHEDULE_RETRY on attempt 3/3 | **BLOCKED** via RULE_FIREWALL_MAX_RETRY_BUDGET_EXHAUSTED | NO_ACTION_ALREADY_STOPPED | Override: True (Ceiling capped) |
| **Hard Decline Misdiagnosis** | SCHEDULE_RETRY on xpired_card | **OVERRIDDEN** via RULE_FIREWALL_HARD_DECLINE_NUDGE_ONLY| NUDGE_PAYMENT_UPDATE | Override: True (Nudge forced) |
| **Malformed Action Token** | "INSTANT_FORCE_CHARGE" (Invalid) | **VALIDATION FAILURE** (Failsafe Handler) | SCHEDULE_RETRY (Safe Backoff) | Failsafe Engaged |

---

## 4. Auditability & Explanations

Every decision recorded in ecovery_audit_log captures:
1. i_diagnosis: The root cause and recovery probability assessed by AI.
2. i_recommendation: What the model recommended.
3. policy_decision: The authorized action passed through the firewall.
4. policy_override_applied: Boolean flag (True/False).
5. policy_override_reason: Explicit human-readable rationale if an override occurred.
