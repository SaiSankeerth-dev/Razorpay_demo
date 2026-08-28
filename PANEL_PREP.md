# Razorpay Panel Interview Preparation — Hard Questions & Honest Answers

> **Razorpay AI Buildathon — Revenue Recovery Track**  
> Technical Defense & System Invariants

---

### Question 1: Out-of-Order Webhooks & Replay Storms
**"What happens if Razorpay delivers `payment.failed` and `subscription.halted` out of order, or re-delivers duplicate webhooks during high network latency?"**

> **Answer:**  
> We handle out-of-order and replayed webhooks through a combination of event-level deduplication and terminal state idempotency. Every raw webhook is stored with its unique `event_id` in `webhook_events`. In the state machine (`subscription_recovery_state`), once a subscription hits attempt #3 or is escalated to `ESCALATED_HUMAN_REVIEW`, the `is_terminal` boolean is permanently set to `True`. Any subsequent or replayed webhook immediately evaluates to `NO_ACTION_ALREADY_STOPPED` without incrementing retry counters or dispatching actions. Where we haven't reached full enterprise hardening yet is distributed locking (e.g., Redis Redlock) for concurrent webhooks arriving within milliseconds of each other—in this version, atomic database row updates handle concurrency within a single instance.

---

### Question 2: Scaling Past 50 Subscriptions to 100,000+ Concurrent Failures
**"How would this architecture scale when processing 100,000 subscription payment failures on the 1st of every month without hitting API rate limits or crashing the worker?"**

> **Answer:**  
> In this prototype, the action engine dispatches retries and nudges inline upon webhook receipt. For production scale (100k+ events/hour), webhooks would push to an append-only distributed queue (such as Apache Kafka or AWS SQS with Celery workers) with a scheduled worker pool. Retries would be grouped into temporal backoff buckets (1h, 6h, 24h) and dispatched via rate-limited worker tasks honoring Razorpay's API rate limits (e.g., 20 RPS) with exponential jitter. The immutable PostgreSQL audit schema is already indexed by `subscription_id` and `created_at` to support partitioned multi-million row scale.

---

### Question 3: Why Hard-Code Compliance Rules Instead of Letting an LLM Decide?
**"Why are compliance guardrails like Do-Not-Disturb hours and opt-outs hard-coded in Python rather than letting an agentic LLM dynamically determine when and how to contact the customer?"**

> **Answer:**  
> Financial recovery is governed by non-negotiable regulatory boundaries (RBI recurring mandate retry frequencies and TRAI Do-Not-Disturb contact hours). Non-deterministic LLM reasoning cannot provide a mathematical zero-hallucination guarantee that a customer will never be messaged at 11:30 PM or that a 4th touch will never be sent to an opted-out user. In regulated enterprise fintech, compliance invariants must be enforced deterministically as code guardrails with 100% test coverage. The LLM's strength lies in communicative flexibility—generating compassionate, personalized email copy and parsing natural language customer date commitments—not in deciding whether regulatory rules apply.

---

### Question 4: Attribution & Preventing False Recovery Claims
**"Why does your dashboard report a 32.28% recovery rate instead of 80%+ like many commercial dunning tools claim, and how do you prevent false recovery attribution?"**

> **Answer:**  
> Many commercial dunning tools artificially inflate recovery numbers by counting any customer who opened an email or was queued for a retry as 'recovered', or by taking credit for natural manual renewals. We implemented strict, conservative revenue attribution: an amount is only counted as recovered if an automated `RETRY_PAYMENT` execution occurred on a `SOFT_DECLINE` subscription AND the live transaction status returned `SUCCESS`. Hard decline nudges, DND holds, and customers awaiting card updates remain classified as unrecovered in the Exceptions Workbench until a verified payment event confirms recovery. This produces a defensible, realistic benchmark (30–35%) aligned with real-world SaaS recovery metrics.

---

### Question 5: Handling Promise-to-Pay Failures & Re-Opened Subscriptions
**"What happens if a customer commits to pay on date $D$, the agent checks in once, but the payment still fails—how does the agent avoid infinite check-in loops or abandoning the account?"**

> **Answer:**  
> Our promise-to-pay engine enforces an explicit state machine transition: `PENDING` $\rightarrow$ `CHECKED_IN` on or after date $D$ with a strict `check_in_count = 1` ceiling. If the check-in occurs and payment has not been received, further automated check-ins are strictly blocked to prevent spamming the customer. Instead, the subscription transitions to `AWAITING_CUSTOMER_UPDATE` or triggers a final escalation to human support in the Exceptions Workbench. A second check-in is never permitted until a fresh webhook arrives or a human operations agent manually resets the commitment state.
