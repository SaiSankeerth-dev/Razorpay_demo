# What Broke — Engineering Case Studies & Root Cause Analyses

> **Engineering Principle:** A running, transparent record of real bugs, broken assumptions, edge cases, and unexpected system behaviors discovered and resolved during development. Every case study includes the root cause, impact, fix, and regression test.

---

### Case Study 1: Raw Bytes vs JSON Re-serialization in Webhook HMAC-SHA256 Verification
* **Failure:** Signature verification failed intermittently on valid Razorpay webhooks when tested through FastAPI endpoint handlers.
* **Root Cause:** Attempting to verify signatures using `json.dumps(payload)` re-serialized JSON keys and altered whitespace (`", "` vs `","`), producing a different byte sequence than the exact payload signed by Razorpay's HMAC generator.
* **Impact:** Legitimate failure webhooks were rejected with HTTP 400.
* **Detection:** `tests/test_signature.py::test_tampered_signature_rejection`.
* **Fix:** Read raw request body bytes (`await request.body()`) directly from the ASGI stream before JSON parsing and verify signatures against the unmodified raw byte sequence.
* **Regression Test:** `tests/test_signature.py::test_valid_signature_with_bytes_body`.
* **Lesson:** In cryptographic webhook ingestion, never parse or re-serialize before signature verification.

---

### Case Study 2: Subscription State Machine Nuance (`pending` vs `halted`)
* **Failure:** Initial system assumed failed recurring billing immediately halted subscriptions.
* **Root Cause:** Razorpay's state machine transitions recurring payments to `pending` during the automated retry window and only transitions to `halted` once all automated retry attempts are exhausted.
* **Impact:** Inaccurate decline classification and inappropriate customer messaging.
* **Detection:** Manual inspection of test-mode webhook payloads.
* **Fix:** Mapped `subscription.pending` to `SOFT_DECLINE` (automated retry backoff) and `subscription.halted` to `HARD_DECLINE` (customer payment method update nudge).
* **Regression Test:** `tests/test_classifier.py::test_classify_soft_decline_subscription_pending` & `tests/test_classifier.py::test_classify_hard_decline_subscription_halted`.
* **Lesson:** Always model domain state machines directly from payment processor lifecycle specifications.

---

### Case Study 3: Replay Webhook Storms on Terminal Subscriptions
* **Failure:** Duplicate failure webhooks sent by Razorpay during network retries re-triggered automated actions on stopped subscriptions.
* **Root Cause:** Decision engine lacked global stopping rule state awareness across replayed events.
* **Impact:** Risk of runaway retries exceeding the 3-attempt ceiling.
* **Detection:** `tests/test_stopping_rules.py::test_replay_webhook_on_terminal_subscription_ignored`.
* **Fix:** Implemented persistent `subscription_recovery_state` table with `is_terminal` flag and `RULE_FIREWALL_TERMINAL_STOP` returning `NO_ACTION_ALREADY_STOPPED` without incrementing counters.
* **Regression Test:** `tests/test_stopping_rules.py::test_replay_webhook_on_terminal_subscription_ignored`.
* **Lesson:** Terminal states must be immutable; replayed webhooks must acknowledge with HTTP 200 without creating state mutations.

---

### Case Study 4: AI Model Financial Boundary Breach (Adversarial Hallucination)
* **Failure:** When an AI model evaluated a card decline with `stolen_card` or `card_blacklisted`, non-deterministic generation occasionally hallucinated that the error was transient and recommended `SCHEDULE_RETRY`.
* **Root Cause:** Unconstrained LLM reasoning cannot guarantee deterministic compliance with financial safety rules.
* **Impact:** Risk of unauthorized debit retries on stolen instruments, resulting in card scheme fines and merchant risk scoring penalties.
* **Detection:** Adversarial test suite evaluating mock hallucinatory LLM outputs.
* **Fix:** Inserted an immutable **Deterministic Policy Firewall** (`agent/policy_firewall.py`) between AI recommendations and execution. AI recommends; policy authorizes. Rule `RULE_FIREWALL_RISK_QUARANTINE` unconditionally overrides model output to `ESCALATE_TO_HUMAN`.
* **Regression Test:** `tests/test_ai_safety_firewall.py::test_adversarial_case1_ai_recommends_retry_on_risk_decline`.
* **Lesson:** AI must never directly execute financial actions or bypass hard deterministic guardrails.

---

### Case Study 5: DND Contact Window Timezone Desynchronization
* **Failure:** Daytime customer nudges at 2:00 PM IST were blocked as outside business hours, while 10:00 PM IST nudges were erroneously dispatched.
* **Root Cause:** Naive `datetime.now()` in standard library defaulted to UTC system clock (where 14:00 IST is 08:30 UTC).
* **Impact:** Severe regulatory DND violations (dispatching customer outreach at night).
* **Detection:** `tests/test_compliance_guardrails.py::test_dnd_window_blocks_and_reschedules_at_11pm`.
* **Fix:** Localized all DND evaluations explicitly to `zoneinfo.ZoneInfo("Asia/Kolkata")` with deterministic 9:00 AM IST next-day rescheduling.
* **Regression Test:** `tests/test_compliance_guardrails.py::test_dnd_window_blocks_and_reschedules_at_11pm`.
* **Lesson:** Compliance window calculations must always be explicitly bound to the cardholder’s local regulatory timezone.

---

### Case Study 6: SMTP Transmission Error Masking vs Transparent Logging
* **Failure:** When SMTP mail relays were unreachable or DNS lookups failed, initial notification executors reported success.
* **Root Cause:** Broad `try...except` blocks swallowed socket exceptions and logged generic warnings.
* **Impact:** Undetected outreach failures and falsified audit trail reporting.
* **Detection:** Test execution in offline sandbox environments.
* **Fix:** Structured `nudge_executor.py` to capture real transport errors (`gaierror: [Errno 11001]`, `ConnectionRefusedError`) and persist them directly into `recovery_audit_log` with `action_result = "FAILED: <error>"`.
* **Regression Test:** `tests/test_phase3_executors.py::test_nudge_sender_email_attempt`.
* **Lesson:** Real-world payment pipelines must record transport-level failure truth rather than papering over delivery errors.

---

### Case Study 7: Lifetime Customer Contact Cap Across Multiple Decline Cycles
* **Failure:** Customers experiencing recurring payment failures across multiple billing cycles received excessive contact messages over their lifetime.
* **Root Cause:** Rate limiting was scoped only per failure incident rather than across the whole subscription lifecycle.
* **Impact:** Customer fatigue, spam complaints, and regulatory harassment violations.
* **Detection:** `tests/test_compliance_guardrails.py::test_lifetime_contact_cap_blocks_contact_n_plus_1`.
* **Fix:** Added monotonic `total_contact_attempts` counter in `subscription_recovery_state`. When count reaches 3, all subsequent nudges across any future decline events are permanently blocked with `BLOCKED_LIFETIME_CAP`.
* **Regression Test:** `tests/test_compliance_guardrails.py::test_lifetime_contact_cap_blocks_contact_n_plus_1`.
* **Lesson:** Anti-harassment rules must enforce global lifetime boundaries, not just transient per-event rate limits.

---

### Case Study 8: Invariant Testing vs Arbitrary Range Assertions
* **Failure:** Recovery rate tests previously used magic ranges such as `assert 20 <= recovery_rate <= 50`.
* **Root Cause:** Lazy test authoring using arbitrary heuristics rather than mathematical invariants.
* **Impact:** Tests could pass even if arithmetic formulas or attribution logic was inverted or corrupted.
* **Detection:** Codebase gap audit.
* **Fix:** Replaced all range assertions with exact mathematical invariants: $\text{recovery\_rate} = (\text{recovered} / \text{eligible}) \times 100$, verifying that recovered revenue strictly equals the sum of successful recovery action amounts and that risk retries are strictly 0.
* **Regression Test:** `tests/test_benchmark_invariants.py::test_invariant_recovery_rate_calculation`.
* **Lesson:** Financial and recovery testing must verify structural and mathematical invariants, never arbitrary percentage brackets.

---

### Case Study 9: Windows CP1252 Stdout Unicode Encoding Breakdown
* **Failure:** Running CLI benchmark scripts crashed with `UnicodeEncodeError: 'charmap' codec can't encode character '\u20b9'`.
* **Root Cause:** Windows command prompt defaults to legacy `cp1252` encoding when printing non-ASCII Indian Rupee symbols (`₹`).
* **Impact:** Evaluation script crashed before completing report generation.
* **Detection:** `python evaluation/benchmark.py test_set.json` execution on Windows shell.
* **Fix:** Explicitly set `encoding="utf-8"` in file writers and standardized stdout formatting to use `INR` or UTF-8 safe output.
* **Regression Test:** `python scripts/run_evaluation.py`.
* **Lesson:** Always specify UTF-8 encoding explicitly in file operations and cross-platform CLI output.

---

### Case Study 10: Concurrent Duplicate Webhook Delivery Race Conditions
* **Failure:** Simultaneous duplicate webhooks arriving within milliseconds on parallel threads could trigger concurrent debit retry API calls.
* **Root Cause:** In-memory local database operations and state lookups were not thread-synchronized.
* **Impact:** Double debit attempts violating idempotency guarantees.
* **Detection:** Multi-threaded parallel stress tests.
* **Fix:** Implemented `threading.RLock()` across all repository state mutations and conditional update guards in `db/repository.py`.
* **Regression Test:** `tests/test_concurrency_idempotency.py::test_concurrent_identical_webhook_delivery_idempotency`.
* **Lesson:** Webhook receivers must enforce thread-safe state synchronization and atomic conditional updates to guarantee exactly-once execution.
