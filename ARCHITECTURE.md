# System Architecture & Technical Specification

> **Core System Invariant:**  
> $$\text{AI Diagnostician Recommends} \longrightarrow \text{Deterministic Policy Firewall Authorizes} \longrightarrow \text{Financial Action Executes}$$

---

## 1. End-to-End System Architecture

```text
                               RAZORPAY WEBHOOKS
                    (payment.failed, subscription.pending/halted)
                                      │
                                      ▼
                        CRYPTOGRAPHIC INGESTION LAYER
                    (HMAC-SHA256 on Raw Request Bytes)
                                      │
                                      ▼
                        RAW EVENT LEDGER (webhook_events)
                                      │
                                      ▼
                       CONTEXT EXTRACTION & CLASSIFIER
                     (3-Tier: Soft / Hard / Risk Precedence)
                                      │
                                      ▼
                       AI DIAGNOSTICIAN (JUDGMENT LAYER)
                 (Root Cause, Recovery Prob P(rec), Delay, Message)
                                      │
                                      │ Validated AIDiagnosisResult
                                      ▼
                  ═════════════════════════════════════════════
                  ████████ DETERMINISTIC POLICY FIREWALL ████████
                  ═════════════════════════════════════════════
                  │ 1. Schema Contract Validation             │
                  │ 2. Risk Quarantine Override (0 Contact)   │
                  │ 3. Max Retry Budget Check (Hard 3/3 Cap)  │
                  │ 4. Replay Idempotency & Terminal Check    │
                  │ 5. Customer Opt-Out Compliance Check      │
                  │ 6. Lifetime Contact Touch Cap (3 Touches) │
                  │ 7. DND Window Hours (9am-8pm IST)         │
                  │ 8. Hard Decline Debit Prevention          │
                  ═════════════════════════════════════════════
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
          AUTHORIZED RETRY     AUTHORIZED NUDGE    BLOCKED: ESCALATE
         (Phase 3 SDK Retry)   (Phase 3 SMTP Link)  (0 Retry, 0 Contact)
                 │                    │                    │
                 └────────────────────┼────────────────────┘
                                      ▼
                        STATE & AUDIT TRAIL PERSISTENCE
                           (recovery_audit_log)
                                      │
                                      ▼
                        EXECUTIVE ANALYTICS DASHBOARD
```

---

## 2. Cryptographic Webhook Ingestion & Idempotency

### Raw Bytes Signature Verification
Razorpay signs webhook payloads using HMAC-SHA256 with a shared secret. Because standard JSON serializers alter key ordering, whitespace separators (`", "` vs `","`), and unicode escaping, signature verification must never parse JSON prior to validation.
```python
# Raw request bytes streamed directly into cryptographic utility
raw_bytes = await request.body()
razorpay.utility.Utility.verify_webhook_signature(
    body=raw_bytes.decode("utf-8"),
    signature=x_razorpay_signature,
    secret=settings.RAZORPAY_WEBHOOK_SECRET
)
```

### Idempotency & Concurrency Synchronization
- Raw payloads are appended to `webhook_events` with their unique `event_id`.
- Subscription lifecycle state is managed in `subscription_recovery_state`.
- All write operations and state transitions are thread-synchronized via `threading.RLock()` to guarantee that concurrent duplicate webhook deliveries result in strictly **1 logical decision and 1 financial execution**.

---

## 3. 3-Tier Decline Classification Taxonomy

Incoming failure codes are categorized into three distinct operational buckets with strict precedence:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ TIER 1: RISK / FRAUD (Precedence 1)                                     │
│ Codes: card_blacklisted, fraud_suspected, payment_risk_check_failed      │
│ Action: Quarantine. Strictly 0 automated retries, 0 customer contacts.  │
├─────────────────────────────────────────────────────────────────────────┤
│ TIER 2: HARD DECLINES (Precedence 2)                                    │
│ Codes: expired_card, token_not_eligible, mandate_revoked, halted        │
│ Action: Automated retries blocked. Queues self-serve update link nudge. │
├─────────────────────────────────────────────────────────────────────────┤
│ TIER 3: SOFT DECLINES (Precedence 3)                                    │
│ Codes: insufficient_funds, gateway_technical_error, subscription.pending│
│ Action: Automated exponential backoff retries (1h, 6h, 24h) up to 3/3.  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. AI Diagnostician & Provider Abstraction

The AI Diagnostician provides semantic judgment where unstructured gateway error descriptions, temporal retry history, and customer value dictate optimal timing.

### Pluggable Provider Architecture
```text
AIProvider (Base Class)
├── LocalAIProvider    (Deterministic semantic rules; 0 API keys; <1ms latency)
├── OpenAIProvider     (Cloud LLM inference with structured JSON schema)
└── MockAIProvider     (Adversarial test injection for safety verification)
```

### Structured Output Contract (`AIDiagnosisResult`)
```json
{
  "failure_diagnosis": "temporary_liquidity_deficit",
  "recovery_probability": 0.88,
  "recommended_action": "SCHEDULE_RETRY",
  "recommended_delay_hours": 1,
  "customer_message_strategy": "NONE",
  "confidence": 0.92,
  "reasoning": "Transient deficit on active card; backoff 1h recommended."
}
```

---

## 5. Deterministic Policy Firewall (Safety Boundary)

AI models are strictly advisory. The Policy Firewall (`agent/policy_firewall.py`) enforces hard mathematical and financial guardrails:

| Guardrail Rule | Trigger Condition | Firewall Action | Safety Invariant Enforced |
| :--- | :--- | :--- | :--- |
| `RULE_FIREWALL_RISK_QUARANTINE` | Classification == `RISK_FLAG` | `ESCALATE_TO_HUMAN` | **Zero retry API calls, zero customer contacts.** |
| `RULE_FIREWALL_MAX_RETRY_BUDGET_EXHAUSTED` | Next Attempt > 3 | `NUDGE_PAYMENT_UPDATE` $\rightarrow$ `STOPPED_MAX_ATTEMPTS` | **Hard cap of 3 automated retry attempts.** |
| `RULE_FIREWALL_TERMINAL_STOP` | Subscription `is_terminal == True` | `NO_ACTION_ALREADY_STOPPED` | **Replayed webhooks ignore execution.** |
| `RULE_FIREWALL_OPT_OUT_GUARDRAIL` | `is_opted_out == True` | `NO_ACTION_ALREADY_STOPPED` | **Customer communication permanently blocked.** |
| `RULE_FIREWALL_LIFETIME_CAP_GUARDRAIL` | Lifetime touches $\ge$ 3 | `BLOCKED_LIFETIME_CAP` | **Anti-harassment ceiling across all billing cycles.** |
| `RULE_FIREWALL_DND_HOLD` | Outside 9:00 AM – 8:00 PM IST | `HOLD_DND` | **Reschedules outreach to 9:00 AM next morning.** |
| `RULE_FIREWALL_HARD_DECLINE_NUDGE_ONLY` | Classification == `HARD_DECLINE` & AI proposed Retry | `NUDGE_PAYMENT_UPDATE` | **Prohibits wasted debits on invalid cards.** |

### Policy Firewall Safety Decision Matrix

| AI Recommendation | System State | Result / Enforcement | Proving Test Case |
| :--- | :--- | :--- | :--- |
| `RETRY` | Safe, budget available | **Execute** (`SCHEDULE_RETRY`) | `tests/test_policy_engine.py::test_policy_soft_decline_attempt_1` |
| `RETRY` | Risk flagged | **Blocked** $\rightarrow$ `ESCALATE_TO_HUMAN` | `tests/test_ai_safety_firewall.py::test_adversarial_case1_ai_recommends_retry_on_risk_decline` |
| `RETRY` | Retry budget exhausted (3/3) | **Blocked** $\rightarrow$ `STOPPED_MAX_ATTEMPTS` | `tests/test_ai_safety_firewall.py::test_adversarial_case3_ai_recommends_retry_after_budget_exhaustion` |
| `CONTACT` | Customer opted out | **Blocked** $\rightarrow$ `NO_ACTION_ALREADY_STOPPED` | `tests/test_ai_safety_firewall.py::test_adversarial_case2_ai_recommends_nudge_on_opted_out_customer` |
| Any | AI provider unavailable | **Safe Deterministic Fallback** | `tests/test_challenger_adversarial_stress.py::test_schema_level_adversarial_rejection_and_fallback` |

---

## 6. Threat Model & Adversarial Containment

The architecture treats all external webhooks, network payloads, and AI model outputs as potentially untrusted:

1. **AI Recommending an Unsafe Action (e.g. retrying stolen card / exhausted budget):** The Deterministic Policy Firewall intercepts the recommendation and forces `ESCALATE_TO_HUMAN` or `STOPPED_MAX_ATTEMPTS`. (*Proved by `tests/test_ai_safety_firewall.py` & `tests/test_challenger_adversarial_stress.py`*).
2. **Malformed AI Output / Schema Failures (e.g. invalid JSON, missing fields, unknown action tokens):** Strict Pydantic parsing rejects invalid payloads, automatically engaging a deterministic fallback policy with zero unauthorized financial actions. (*Proved by `tests/test_challenger_adversarial_stress.py::test_schema_level_adversarial_rejection_and_fallback`*).
3. **Duplicate / Replayed Webhooks:** The global stopping rule (`RULE_FIREWALL_TERMINAL_STOP`) identifies terminal subscriptions and returns `NO_ACTION_ALREADY_STOPPED` without incrementing counters or double-debiting. (*Proved by `tests/test_stopping_rules.py` & `tests/test_concurrency_idempotency.py`*).
4. **Concurrent Webhook Delivery Race Conditions:** Atomic critical sections are guarded by `threading.RLock()` in `db/repository.py`, guaranteeing serialized state transitions and idempotent execution under parallel thread contention. (*Proved by `tests/test_concurrency_idempotency.py::test_concurrent_identical_webhook_delivery_idempotency` & `tests/test_challenger_adversarial_stress.py::test_high_contention_concurrency_single_subscription`*).

---

## 7. Single Continuous Decision-to-Outcome Audit Ledger

Every transaction failure creates or updates a single unified audit entry in `recovery_audit_log`:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID | Unique immutable primary key |
| `subscription_id` | String | Razorpay subscription identifier |
| `event_id` | String | Webhook event identifier |
| `decline_bucket` | Enum | `SOFT_DECLINE`, `HARD_DECLINE`, `RISK_FLAG` |
| `ai_diagnosis` | String | Semantic failure diagnosis from AI layer |
| `ai_recovery_prob` | Float | Estimated recovery likelihood $P(\text{recovery}) \in [0, 1]$ |
| `ai_confidence` | Float | Calibrated model confidence |
| `policy_decision` | Enum | Authorized action authorized by Policy Firewall |
| `policy_override_applied`| Boolean | `True` if Policy Firewall intercepted an unsafe AI action |
| `policy_rule_id` | String | Exact rule identifier enforcing the authorization |
| `action_executed` | String | Physical action dispatched (`RETRY_PAYMENT`, `SEND_NUDGE`, `ESCALATE`) |
| `action_result` | String | Final outcome (`SUCCESS`, `FAILED: <reason>`, `BLOCKED`) |
| `created_at` | Timestamp | UTC timestamp of event processing |

---

## 8. Evaluation Methodology & 3-Arm Benchmark Specification

### Dataset Generation (1,000 Scenarios)
Generated via `evaluation/dataset_generator.py` with fixed random seed (`seed=42`):
- **50% Soft Declines (500 cases):** Insufficient funds, gateway timeouts, temporary bank errors.
- **25% Risk Flags (250 cases):** Stolen cards, blacklisted instruments, issuer risk checks.
- **25% Hard Declines (250 cases):** Expired cards, deleted tokens, revoked mandates.

### Data Splits
- **Development Set (70%, 700 cases):** Algorithm calibration and rule development (`evaluation/data/dev_set.json`).
- **Validation Set (15%, 150 cases):** Threshold tuning (`evaluation/data/val_set.json`).
- **Held-Out Test Set (15%, 150 cases):** **Unseen 3-arm benchmark evaluation (`evaluation/data/test_set.json`).**

### Three Comparative Arms
1. **Arm 1: Naive Fixed-Schedule Retry (Baseline):** Blind 24-hour retries up to 3 attempts with 0 decline awareness, 0 customer nudging, and illegal retry attempts on fraud-flagged instruments.
2. **Arm 2: Rules-Only (Phase 2 Classifier + Policy Engine):** 3-tier decline classification and deterministic backoff rules without AI semantic reasoning (generic payment update nudges).
3. **Arm 3: Decline-Aware AI Agent + Policy Firewall:** AI failure diagnosis, empirical recovery probability estimation, and customer messaging strategies + Deterministic Policy Firewall.

### Mathematical Formulations
1. **Recovery Rate (%):**
   $$\text{Recovery Rate} = \left(\frac{\text{Total Recovered Revenue (INR)}}{\text{Total Revenue at Risk (INR)}}\right) \times 100$$
2. **Incremental Recovered Revenue vs Baseline (INR):**
   $$\Delta \text{Revenue}_{\text{Baseline}} = \text{Agent Recovered (₹183,940.00)} - \text{Baseline Recovered (₹137,955.00)} = +\mathbf{\text{INR } 45,985.00 \text{ (+9.40pp absolute gain)}}$$
3. **Incremental Recovered Revenue vs Rules-Only (INR):**
   $$\Delta \text{Revenue}_{\text{Rules}} = \text{Agent Recovered (₹183,940.00)} - \text{Rules-Only Recovered (₹165,447.00)} = +\mathbf{\text{INR } 18,493.00 \text{ (+3.78pp absolute gain)}}$$
4. **Unnecessary Retries Avoided:**
   $$\text{Retries Avoided} = \text{Baseline Retries (403)} - \text{Agent Retries (178)} = \mathbf{225 \text{ retries}}$$
5. **Risk Violations Prevented:**
   $$\text{Risk Retries Prevented} = 114 \text{ baseline violations} - 0 \text{ agent retries} = \mathbf{114 \text{ (100\% isolation)}}$$


