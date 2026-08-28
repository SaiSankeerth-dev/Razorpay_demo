# Razorpay AI Revenue Recovery Agent — Current State Audit

**Audit Date:** 2026-08-28  
**Repository:** Razorpay_demo  
**Track:** AI Revenue Recovery (Razorpay AI Builder 2026)  
**Auditor:** Senior Lead Systems & AI Engineer  

---

## 1. Executive Summary

This audit establishes the ground truth baseline of the repository prior to implementing the AI Diagnostician and benchmarking suite.
The system currently possesses strong deterministic foundations: cryptographic webhook ingestion, 3-tier error taxonomy classification, fixed exponential backoff retry scheduling, compliance guardrails (DND, opt-outs, lifetime contact limits), and continuous audit trail logging.

However, the repository currently lacks a genuine AI reasoning and diagnostic layer, provider abstraction, automated AI safety containment evaluation, a naive recovery baseline, an invariant-tested benchmark against dirty datasets, and concurrency regression tests.

---

## A. What Already Works (Verified Baseline)

| Component | Relevant File(s) | Current Behavior | Verification Method | Result |
| :--- | :--- | :--- | :--- | :--- |
| **Cryptographic Webhook Ingestion** | webhooks/verifier.py, webhooks/server.py | Validates HMAC-SHA256 signatures over raw request bytes; rejects tampered bodies, invalid secrets, and missing headers; stores raw JSONB events. | pytest tests/test_signature.py tests/test_webhooks.py (6 tests) | **PASSED** (100% rejection of tampered payloads) |
| **3-Tier Decline Classifier** | gent/classifier.py | Classifies Razorpay webhook payloads into SOFT_DECLINE, HARD_DECLINE, and RISK_FLAG based on error code taxonomy and notes. | pytest tests/test_classifier.py (8 tests) | **PASSED** (Deterministic mapping verified) |
| **Deterministic Policy Engine** | gent/policy_engine.py | Schedules progressive exponential backoff (1h, 6h, 24h) for soft declines; caps retries at 3; blocks replayed webhooks on terminal states. | pytest tests/test_policy_engine.py tests/test_stopping_rules.py (8 tests) | **PASSED** (Strict 3-attempt ceiling enforced) |
| **Compliance Guardrails** | gent/compliance.py | Enforces DND hours (9:00 AM – 8:00 PM Asia/Kolkata), customer opt-outs, and 3-touch lifetime contact cap. | pytest tests/test_compliance_guardrails.py (3 tests) | **PASSED** (11 PM nudges held & rescheduled to 9 AM) |
| **Recovery Action Executors** | gent/action_engine.py, gent/executors/* | Dispatches test-mode API retries (etry_executor.py), SMTP email nudges (
udge_executor.py), zero-contact risk escalation, and promise-to-pay check-ins. | pytest tests/test_phase3_executors.py tests/test_promise_to_pay.py (5 tests) | **PASSED** (Real transport & SDK integration verified) |
| **Batch Simulation & Dashboard UI** | scripts/generate_batch_data.py, webhooks/server.py, dashboard/app/page.tsx | Simulates 60 test subscriptions through the real pipeline; renders live metrics, SQL queries, Capital Flow Bar, and Exceptions Workbench. | pytest tests/test_batch_and_dashboard.py (4 tests) | **PASSED** (Reconciled ₹190,440 at risk, ₹61,482 recovered) |

**Total Verified Existing Test Suite:** **41 / 41 Tests Passing** in 7.48s.

---

## B. What is Missing (Gap Analysis)

1. **Genuine AI Reasoning & Diagnostics:**
   - The current classifier.py and policy_engine.py rely purely on static dictionary lookups (RISK_FLAG_REASONS, SOFT_DECLINE_REASONS).
   - Missing: An AI Diagnostician that estimates failure cause context, predicts empirical recovery probabilities ((\text{recovery})$), determines dynamic retry delay recommendations, evaluates customer communication strategies, and provides structured diagnostic explanations.

2. **Pluggable AI Provider Architecture:**
   - Missing: A unified AIProvider interface supporting LocalAIProvider, OpenAIProvider (when API keys are present), and an offline deterministic RuleBasedAIProvider / MockAIProvider for fully reproducible offline execution.

3. **AI Safety Model & Deterministic Policy Firewall:**
   - Architecture requirement: **AI Recommends $\rightarrow$ Deterministic Policy Authorizes**.
   - Missing: Explicit Policy Firewall intermediate layer that schema-validates AI recommendations and strictly checks Risk Quarantine, Compliance (DND/Opt-Out/Lifetime Cap), Retry Budget, and Idempotency before authorizing any action.
   - Missing: docs/AI_SAFETY_MODEL.md.

4. **AI Evaluation Framework:**
   - Missing: Reproducible evaluation framework that measures:
     - Diagnosis Accuracy (%)
     - Intervention Selection Accuracy (%)
     - Confidence Calibration
     - Unsafe AI Recommendations Containment Rate (100% blocked by policy)
     - Schema Validation Failure Handling

5. **Expanded & Realistic Synthetic Dataset (500–1,000 Scenarios):**
   - Current dataset has only 60 clean subscriptions.
   - Missing: Large-scale dataset with 500–1,000 scenarios containing dirty edge cases: network timeout spikes, bank maintenance windows, duplicate webhook races, out-of-order event delivery, customer opt-outs mid-recovery, repeated soft declines, and promise-to-pay commitments.

6. **Held-Out Evaluation Split:**
   - Missing: Formal split (70% Development, 15% Validation, 15% Held-Out Evaluation) documented in docs/EVALUATION.md.

7. **Naive Baseline Comparison (valuation/baselines/naive_retry.py):**
   - Missing: Standard industry baseline representing naive fixed-schedule retry (retrying every failure every 24h with no decline awareness or risk isolation).

8. **Measured Financial Recovery & Benchmark Output:**
   - Missing: Automated comparative benchmark generator computing:
     - Total Revenue at Risk (INR)
     - Baseline vs Agent Recovered Revenue (INR)
     - Incremental Revenue Recovered (INR)
     - Baseline vs Agent Recovery Rate (%)
     - Unnecessary Retries Avoided
     - Risk Retries Prevented (0 for Agent vs >0 for Naive)
     - Outputting to valuation/results/benchmark.json and valuation/results/benchmark.md.

9. **Adversarial AI Safety Tests:**
   - Missing: Targeted unit tests proving that when AI hallucinates or recommends unsafe actions (e.g. retry on stolen card, nudge on opted-out user, retry on 3/3 attempts, or invalid action syntax), the Policy Firewall unconditionally blocks execution.

10. **Concurrency & Race Condition Verification:**
    - Missing: Concurrency regression test executing parallel concurrent threads with duplicate webhook events on the same subscription ID to prove exact-once idempotency (1 logical action, 0 double debits).

11. **Enhanced Audit Trail Schema:**
    - ecovery_audit_log needs explicit columns/fields for i_diagnosis, i_confidence, i_recommendation, policy_decision, policy_reason, ction_executed, ction_result, and ecovered_amount.

12. **Dashboard Visual Upgrades:**
    - Needs explicit comparative cards: Baseline vs AI Incremental ARR, AI Diagnostic Accuracy, Recovery Funnel, and an interactive Decision Timeline highlighting an AI recommendation blocked by policy.

13. **One-Command Evaluation & Demo Scripts:**
    - Missing: python scripts/run_evaluation.py and python scripts/run_demo.py.

14. **Documentation Polish & Substantiation:**
    - Missing: LIMITATIONS.md, docs/PITCH.md, docs/PANEL_QA.md, updated case studies in WHAT_BROKE.md, and refreshed README.md.

---

## C. Risk Register

| # | Risk Description | Severity | Evidence / Trigger | Recommended Fix |
| :- | :--- | :--- | :--- | :--- |
| **R1** | **Unbounded AI Financial Execution** | **CRITICAL** | If an LLM directly calls Razorpay retry or sends nudges, hallucinations could cause unauthorized debits or regulatory violations. | Insert strict Deterministic Policy Firewall between AI recommendation and action execution. AI recommends; policy authorizes. |
| **R2** | **Fabricated Benchmark Claims** | **HIGH** | Hardcoded recovery rates or unsubstantiated claims damage credibility with hackathon judges. | Build dynamic evaluation engine that computes all metrics directly from dataset execution into enchmark.json. |
| **R3** | **Paid API Dependency Breakdown** | **HIGH** | Evaluators without OpenAI/Anthropic API keys could face runtime failures. | Implement pluggable AIProvider with default deterministic LocalAIProvider/MockAIProvider requiring 0 external keys. |
| **R4** | **Concurrency Race Conditions** | **MEDIUM** | Simultaneous duplicate webhooks could trigger concurrent retry API calls if state checks aren't thread-safe/atomic. | Add thread-level locking / atomic conditional update guards in repository and concurrency unit test. |
| **R5** | **Overfitting to Clean 60-Sub Batch** | **MEDIUM** | 60 clean synthetic items do not prove resilience against dirty production edge cases. | Extend generator to 500–1,000 scenarios with held-out splits (70/15/15). |

---

## D. Architecture Implementation Plan

`	ext
                               RAZORPAY TEST MODE / WEBHOOKS
                                             │
                                             ▼
                                     WEBHOOK INGESTION
                                    (HMAC + Idempotency)
                                             │
                                             ▼
                                   PAYMENT/USER CONTEXT
                                             │
                                             ▼
                                      AI DIAGNOSTICIAN
                              (Failure Cause, P(rec), Strategy)
                                             │
                                             ▼
                                  STRUCTURED RECOMMENDATION
                                (Validated Pydantic Schema)
                                             │
                                             ▼
                                  DETERMINISTIC FIREWALL
                       (Risk Check, DND, Opt-Out, Cap, Retry Budget)
                                             │
                       ┌─────────────────────┼─────────────────────┐
                       ▼                     ▼                     ▼
                APPROVE: RETRY        APPROVE: NUDGE        BLOCK: ESCALATE
                       │                     │                     │
                       └─────────────────────┼─────────────────────┘
                                             ▼
                                      ACTION EXECUTOR
                                             │
                                             ▼
                                  CONTINUOUS AUDIT LEDGER
                                             │
                                             ▼
                                     EVALUATION ENGINE
                               (Baseline vs AI Agent Metrics)
`

Audit completed and approved. Ready to proceed with Step 2 implementation.
