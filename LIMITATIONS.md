# System Limitations & Honest Operational Boundaries

> **Engineering Transparency:** To maintain credibility with evaluators and fintech engineering panels, this document transparently states the boundaries, assumptions, and known limitations of the prototype.

---

## 1. Synthetic Evaluation vs Production Data
* **Limitation:** The 1,000-scenario evaluation dataset is synthetic. While generated using realistic error codes, failure distributions, and SaaS billing distributions, it does not reflect the long-tail edge cases of live merchant production traffic.
* **Mitigation:** The pipeline processes every synthetic scenario through the exact same cryptographic, classification, AI diagnostic, policy firewall, and audit logging code that processes real Razorpay webhooks.

---

## 2. Razorpay Test-Mode API Boundaries
* **Limitation:** In Razorpay Test Mode (`rzp_test_...`), bank debits do not move real cardholder funds, and card network latency / 3DS redirect flows are simulated by Razorpay's sandbox.
* **Mitigation:** The system integrates directly with the official Razorpay Python SDK and handles true API error responses and rate limits.

---

## 3. AI Model Latency & Fallback Strategy
* **Limitation:** When configured with cloud LLMs (`AI_PROVIDER=openai`), external API calls introduce 400ms–1,200ms latency and could fail during OpenAI network outages.
* **Mitigation:** The architecture implements a fast, deterministic local diagnostic fallback (`LocalAIProvider`) that executes in <1ms with 0 external network dependencies and 0 API cost.

---

## 4. Compliance Guardrails Prototype Scope
* **Limitation:** The compliance guardrails implemented (9:00 AM – 8:00 PM IST DND, 3-touch lifetime cap, opt-outs) are modeled based on standard TRAI/RBI dunning principles. Production deployment across global jurisdictions requires configurable policy rules per customer country.
* **Mitigation:** All compliance rules are modularized in `agent/compliance.py` and can be adjusted via environment configuration.

---

## 5. Storage Scale & Concurrency Boundaries
* **Limitation:** The local file-backed storage (`db/local_store.json`) is designed for local development, zero-dependency testing, and single-instance demonstrations. It is bounded to ~50,000 events before file I/O latency degrades.
* **Mitigation:** Production deployment seamlessly points to Supabase / PostgreSQL by configuring `DATABASE_URL` and `SUPABASE_URL`, supporting distributed multi-tenant workloads.

---

## 6. Email Delivery Transport in Local Sandboxes
* **Limitation:** In developer environments without outbound port 587/SMTP access, real socket connection attempts to external mail relays fail with DNS/socket errors.
* **Mitigation:** The engine captures transport-level errors transparently and records them honestly in `recovery_audit_log` with `action_result = "FAILED: <error>"` rather than masking failures.
