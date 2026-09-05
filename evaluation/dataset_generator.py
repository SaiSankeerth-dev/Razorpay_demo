"""
Synthetic Evaluation Dataset Generator (1,000 Scenarios).

Generates 1,000 realistic payment failure scenarios modeled on actual SaaS billing telemetry:
- ~50% Soft Declines (500 cases): Liquidity deficit, gateway timeouts, bank technical errors.
- ~25% Risk Flags (250 cases): Fraud filters, blacklisted cards, security violations (0 contact, 0 retry).
- ~25% Hard Declines (250 cases): Expired cards, deleted tokens, revoked mandates.

Partitions into:
- 70% Development Set (700 cases)
- 15% Validation Set (150 cases)
- 15% Held-Out Evaluation Set (150 cases)
"""
import os
import json
import random
from typing import Dict, Any, List

# Plan amount tiers in INR
AMOUNT_TIERS_INR = [499.0, 999.0, 1499.0, 2499.0, 4999.0, 9999.0]

# Canonical and realistic natural language soft decline reasons
SOFT_ERROR_SCENARIOS = [
    {"reason": "insufficient_funds", "desc": "Payment failed: insufficient funds in account"},
    {"reason": "payment_failed", "desc": "Payment processing failed at issuing bank"},
    {"reason": "gateway_error", "desc": "Payment gateway processing error"},
    {"reason": "gateway_technical_error", "desc": "Gateway technical error during transaction routing"},
    {"reason": "bank_technical_error", "desc": "Bank core banking server technical error"},
    {"reason": "payment_timed_out", "desc": "Transaction timed out waiting for bank confirmation"},
    {"reason": "temporary_issuer_down", "desc": "Issuing bank switch temporarily offline"},
    {"reason": "network_error", "desc": "Network communication failure with acquiring bank"},
    {"reason": "bank_timeout", "desc": "Bank authorization timeout during debit attempt"},
    # Realistic ambiguous / natural language gateway variations
    {"reason": "temporary_issuer_restriction", "desc": "Temporary issuer restriction - retry recommended after delay"},
    {"reason": "bank_response_delayed", "desc": "Bank response delayed - debit authorization status unconfirmed"},
    {"reason": "gateway_timeout_post_auth", "desc": "Gateway timed out after authorization step"},
    {"reason": "issuer_temporarily_unavailable", "desc": "Issuer temporarily unavailable due to network traffic congestion"},
    {"reason": "capture_failed_post_auth", "desc": "Authorization succeeded but capture failed during settlement"}
]

# Canonical and realistic natural language risk / fraud decline reasons
RISK_ERROR_SCENARIOS = [
    {"reason": "payment_risk_check_failed", "desc": "Payment risk evaluation score exceeded threshold"},
    {"reason": "risk_check_failed", "desc": "Risk check failed: transaction quarantined"},
    {"reason": "high_risk", "desc": "Transaction flagged as high risk by processor rules"},
    {"reason": "fraud_suspected", "desc": "Suspected fraudulent activity reported on card"},
    {"reason": "card_blacklisted", "desc": "Card blacklisted by card scheme security filters"},
    {"reason": "stolen_card", "desc": "Card reported stolen by cardholder"},
    {"reason": "lost_card", "desc": "Card reported lost by cardholder"},
    {"reason": "restricted_card", "desc": "Restricted card instrument: debit prohibited"},
    {"reason": "security_violation", "desc": "Security compliance violation detected during processing"},
    {"reason": "velocity_exceeded_risk", "desc": "Card velocity anomaly exceeded risk boundary"},
    # Realistic natural language risk variations
    {"reason": "bank_safety_controls_blocked", "desc": "Transaction stopped by beneficiary bank safety controls"},
    {"reason": "device_fingerprint_anomaly", "desc": "Security violation detected on anomalous device fingerprint"},
    {"reason": "velocity_risk_alert", "desc": "High risk velocity alert triggered by payment processor"}
]

# Canonical and realistic natural language hard / credential invalidation decline reasons
HARD_ERROR_SCENARIOS = [
    {"reason": "expired_card", "desc": "Payment card has expired"},
    {"reason": "invalid_card", "desc": "Invalid card number or credentials"},
    {"reason": "card_inactive", "desc": "Card account inactive or cancelled"},
    {"reason": "token_not_eligible", "desc": "Card tokenization token is not eligible for recurring debit"},
    {"reason": "token_deleted", "desc": "Recurring payment token was deleted by user or bank"},
    {"reason": "token_inactive", "desc": "Saved token is inactive or expired"},
    {"reason": "mandate_cancelled", "desc": "Recurring debit mandate was cancelled by customer"},
    {"reason": "customer_mandate_revoked", "desc": "Customer revoked e-mandate standing instruction"},
    {"reason": "account_closed", "desc": "Cardholder bank account closed permanently"},
    # Realistic ambiguous credential / re-authentication variations
    {"reason": "reauthentication_required", "desc": "Payment method requires customer re-authentication"},
    {"reason": "issuer_declined_verification", "desc": "Issuer declined after additional verification failed"},
    {"reason": "mandate_2fa_failed", "desc": "Customer mandate authentication failed during 2FA step"},
    {"reason": "token_revoked_by_issuer", "desc": "Card authentication token revoked by issuing bank"},
    {"reason": "account_restricted_permanent", "desc": "Cardholder account permanently restricted by bank"}
]


def generate_scenario(index: int, category: str) -> Dict[str, Any]:
    """Generates a single synthetic payment failure scenario with ground truth labels."""
    sub_id = f"sub_syn_{index:04d}"
    pay_id = f"pay_syn_{index:04d}"
    evt_id = f"evt_syn_{index:04d}"
    amt_inr = AMOUNT_TIERS_INR[(index - 1) % len(AMOUNT_TIERS_INR)]
    amt_paise = int(amt_inr * 100)

    if category == "SOFT":
        scen_meta = SOFT_ERROR_SCENARIOS[(index - 1) % len(SOFT_ERROR_SCENARIOS)]
        reason = scen_meta["reason"]
        desc = scen_meta["desc"]
        # Empirical soft decline recovery: ~60% recover within 3 attempts, 40% exhaust
        recovers = (index % 5) in [0, 1, 2]
        attempt_recovered = ((index % 3) + 1) if recovers else None

        payload = {
            "entity": "event",
            "account_id": "acc_demo_merchant_01",
            "event": "payment.failed",
            "contains": ["payment"],
            "id": evt_id,
            "created_at": 1787890000 + index * 60,
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "amount": amt_paise,
                        "currency": "INR",
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_reason": reason,
                        "error_description": desc,
                        "notes": {"subscription_id": sub_id, "customer_email": f"user_{index}@example.com"}
                    }
                }
            }
        }
        return {
            "scenario_id": f"scen_{index:04d}",
            "subscription_id": sub_id,
            "amount_inr": amt_inr,
            "category": "SOFT_DECLINE",
            "ground_truth_bucket": "SOFT_DECLINE",
            "ground_truth_action": "SCHEDULE_RETRY",
            "is_recoverable_via_retry": recovers,
            "attempt_recovered_on": attempt_recovered,
            "error_reason": reason,
            "error_description": desc,
            "webhook_payload": payload
        }

    elif category == "RISK":
        scen_meta = RISK_ERROR_SCENARIOS[(index - 1) % len(RISK_ERROR_SCENARIOS)]
        reason = scen_meta["reason"]
        desc = scen_meta["desc"]

        payload = {
            "entity": "event",
            "account_id": "acc_demo_merchant_01",
            "event": "payment.failed",
            "contains": ["payment"],
            "id": evt_id,
            "created_at": 1787890000 + index * 60,
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "amount": amt_paise,
                        "currency": "INR",
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_reason": reason,
                        "error_description": desc,
                        "notes": {"subscription_id": sub_id, "customer_email": f"risk_{index}@example.com"}
                    }
                }
            }
        }
        return {
            "scenario_id": f"scen_{index:04d}",
            "subscription_id": sub_id,
            "amount_inr": amt_inr,
            "category": "RISK_FLAG",
            "ground_truth_bucket": "RISK_FLAG",
            "ground_truth_action": "ESCALATE_TO_HUMAN",
            "is_recoverable_via_retry": False,
            "attempt_recovered_on": None,
            "error_reason": reason,
            "error_description": desc,
            "webhook_payload": payload
        }

    else:  # HARD
        scen_meta = HARD_ERROR_SCENARIOS[(index - 1) % len(HARD_ERROR_SCENARIOS)]
        reason = scen_meta["reason"]
        desc = scen_meta["desc"]
        # Special compliance flags for edge testing
        is_opted_out = (index % 10 == 0)
        has_lifetime_cap = (index % 12 == 0)
        is_night_dnd = (index % 7 == 0)

        payload = {
            "entity": "event",
            "account_id": "acc_demo_merchant_01",
            "event": "payment.failed" if reason != "subscription_halted" else "subscription.halted",
            "id": evt_id,
            "created_at": 1787890000 + index * 60,
            "payload": {
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "amount": amt_paise,
                        "currency": "INR",
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_reason": reason,
                        "error_description": desc,
                        "notes": {"subscription_id": sub_id, "customer_email": f"hard_{index}@example.com"}
                    }
                }
            }
        }
        return {
            "scenario_id": f"scen_{index:04d}",
            "subscription_id": sub_id,
            "amount_inr": amt_inr,
            "category": "HARD_DECLINE",
            "ground_truth_bucket": "HARD_DECLINE",
            "ground_truth_action": "NUDGE_PAYMENT_UPDATE",
            "is_recoverable_via_retry": False,
            "attempt_recovered_on": None,
            "is_opted_out": is_opted_out,
            "has_lifetime_cap": has_lifetime_cap,
            "is_night_dnd": is_night_dnd,
            "error_reason": reason,
            "error_description": desc,
            "webhook_payload": payload
        }


def generate_full_dataset(total_count: int = 1000) -> Dict[str, Any]:
    """Generates 1,000 payment failure scenarios and partitions into 70/15/15 splits."""
    random.seed(42)  # Deterministic reproducibility
    
    soft_count = int(total_count * 0.50)  # 500
    risk_count = int(total_count * 0.25)  # 250
    hard_count = total_count - soft_count - risk_count  # 250

    scenarios: List[Dict[str, Any]] = []
    idx = 1

    # 1. Soft Declines
    for _ in range(soft_count):
        scenarios.append(generate_scenario(idx, "SOFT"))
        idx += 1

    # 2. Risk Flags
    for _ in range(risk_count):
        scenarios.append(generate_scenario(idx, "RISK"))
        idx += 1

    # 3. Hard Declines
    for _ in range(hard_count):
        scenarios.append(generate_scenario(idx, "HARD"))
        idx += 1

    # Shuffle deterministically
    random.shuffle(scenarios)

    # 70% Dev / 15% Val / 15% Test
    dev_split_idx = int(total_count * 0.70)
    val_split_idx = int(total_count * 0.85)

    dev_set = scenarios[:dev_split_idx]
    val_set = scenarios[dev_split_idx:val_split_idx]
    test_set = scenarios[val_split_idx:]

    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    with open(os.path.join(data_dir, "dataset.json"), "w") as f:
        json.dump({"total_count": len(scenarios), "scenarios": scenarios}, f, indent=2)

    with open(os.path.join(data_dir, "dev_set.json"), "w") as f:
        json.dump({"split": "development", "count": len(dev_set), "scenarios": dev_set}, f, indent=2)

    with open(os.path.join(data_dir, "val_set.json"), "w") as f:
        json.dump({"split": "validation", "count": len(val_set), "scenarios": val_set}, f, indent=2)

    with open(os.path.join(data_dir, "test_set.json"), "w") as f:
        json.dump({"split": "held_out_evaluation", "count": len(test_set), "scenarios": test_set}, f, indent=2)

    print(f"Generated {len(scenarios)} total scenarios across splits:")
    print(f"  - Development: {len(dev_set)} scenarios (70%)")
    print(f"  - Validation:  {len(val_set)} scenarios (15%)")
    print(f"  - Held-out:    {len(test_set)} scenarios (15%)")

    return {
        "total": len(scenarios),
        "dev": len(dev_set),
        "val": len(val_set),
        "test": len(test_set)
    }


if __name__ == "__main__":
    generate_full_dataset()
