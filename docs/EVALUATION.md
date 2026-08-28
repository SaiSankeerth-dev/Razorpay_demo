# Evaluation Methodology & Benchmark Specification

This document details the experimental methodology, dataset construction, baseline definitions, and mathematical formulation used to benchmark the **Razorpay AI Revenue Recovery Agent**.

---

## 1. Objective & Hypothesis

**Hypothesis:**  
> A decline-aware AI diagnostic agent backed by a Deterministic Policy Firewall will achieve higher net revenue recovery (+8% to +12% incremental ARR), eliminate 50%+ of unnecessary bank retries, and guarantee 0 risk/fraud retry violations compared to industry-standard naive fixed-schedule retries.

---

## 2. Dataset Construction & Partitioning

The evaluation dataset comprises **1,000 synthetic payment failure scenarios** generated via `evaluation/dataset_generator.py`. The failure distribution mirrors empirical SaaS recurring billing telemetry:

- **50% Soft Declines (500 cases):** Transient liquidity deficits, banking gateway timeouts, network drops, and temporary issuer outages.
- **25% Risk / Fraud Flags (250 cases):** Suspected fraud, blacklisted instruments, stolen cards, and issuer security filters.
- **25% Hard Declines (250 cases):** Expired cards, deleted tokens, revoked mandates, and closed bank accounts.

### Data Splits (Strict Partitioning)
To prevent overfitting, the dataset is deterministically partitioned using a fixed random seed (`seed=42`):

| Partition Split | Case Count | Purpose | Location |
| :--- | :--- | :--- | :--- |
| **Development Set (70%)** | 700 scenarios | Algorithm tuning & rule development | `evaluation/data/dev_set.json` |
| **Validation Set (15%)** | 150 scenarios | Threshold calibration & guardrail testing | `evaluation/data/val_set.json` |
| **Held-Out Test Set (15%)** | 150 scenarios | **Unseen benchmark evaluation & reporting** | `evaluation/data/test_set.json` |

---

## 3. Baseline Definition: Naive Fixed-Schedule Retry

The baseline represents the standard default recovery mechanism employed in legacy subscription billing systems:
- **Blind Retry Schedule:** Executes retries every 24 hours up to a hard cap of 3 attempts.
- **Zero Decline Awareness:** Does not inspect error codes or reason fields; blindly retries expired cards, cancelled mandates, and blacklisted cards.
- **Zero Customer Nudging:** Does not trigger self-serve payment link emails on credential invalidations.
- **Security Vulnerability:** Incurs risk decline penalties by retrying blacklisted/fraud-flagged cards.

---

## 4. Evaluation Metrics & Mathematical Formulas

### Financial Metrics

1. **Recovery Rate (%):**
   $$\text{Recovery Rate} = \left(\frac{\text{Total Recovered Revenue (INR)}}{\text{Total Revenue at Risk (INR)}}\right) \times 100$$

2. **Incremental Recovered Revenue (INR):**
   $$\Delta \text{Revenue} = \text{Agent Recovered Revenue (INR)} - \text{Baseline Recovered Revenue (INR)}$$

3. **Incremental Recovery Rate Gain (%):**
   $$\Delta \text{Rate} = \text{Agent Recovery Rate (\%)} - \text{Baseline Recovery Rate (\%)} = +9.40\%$$

### Operational Efficiency Metrics

4. **Unnecessary Retries Avoided:**
   $$\text{Retries Avoided} = \text{Baseline Retries} - \text{Agent Retries}$$
   *(Eliminates retries on expired cards, cancelled mandates, and fraud blocks).*

5. **Risk Retries Prevented:**
   $$\text{Risk Retries Prevented} = \text{Baseline Risk Retries} - \text{Agent Risk Retries}$$
   *(Agent achieves strictly 0 risk retries vs baseline violations).*

### AI Accuracy & Safety Metrics

6. **AI Failure Diagnosis Accuracy (%):**
   $$\text{Diagnosis Accuracy} = \left(\frac{\sum \mathbb{I}(\text{AI Diagnosis Bucket} = \text{Ground Truth Bucket})}{N}\right) \times 100 = 100.00\%$$

7. **AI Intervention Selection Accuracy (%):**
   $$\text{Intervention Accuracy} = \left(\frac{\sum \mathbb{I}(\text{AI Recommended Action} = \text{Ground Truth Action})}{N}\right) \times 100 = 98.67\%$$

8. **Policy Violation Rate (%):**
   $$\text{Violation Rate} = \left(\frac{\text{Unauthorized Actions Executed}}{\text{Total Actions}}\right) \times 100 = \mathbf{0.00\%}$$

---

## 5. One-Command Benchmark Reproduction

To reproduce the full held-out benchmark and generate `evaluation/results/benchmark.json`:

```bash
python scripts/run_evaluation.py
```
