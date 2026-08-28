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

SOFT_ERROR_REASONS = [
    "insufficient_funds",
    "payment_failed",
    "gateway_error",
    "gateway_technical_error",
    "bank_technical_error",
    "payment_timed_out",
    "temporary_issuer_down",
    "network_error",
    "bank_timeout"
]

RISK_ERROR_REASONS = [
    "payment_risk_check_failed",
    "risk_check_failed",
    "high_risk",
    "fraud_suspected",
    "card_blacklisted",
    "stolen_card",
    "lost_card",
    "restricted_card",
    "security_violation",
    "velocity_exceeded_risk"
]

HARD_ERROR_REASONS = [
    "expired_card",
    "invalid_card",
    "card_inactive",
    "token_not_eligible",
    "token_deleted",
    "token_inactive",
    "mandate_cancelled",
    "customer_mandate_revoked",
    "account_closed"
]


def generate_scenario(index: int, category: str) -> Dict[str, Any]:
    """Generates a single synthetic payment failure scenario with ground truth labels."""
    sub_id = f"sub_syn_{index:04d}"
    pay_id = f"pay_syn_{index:04d}"
    evt_id = f"evt_syn_{index:04d}"
    amt_inr = AMOUNT_TIERS_INR[(index - 1) % len(AMOUNT_TIERS_INR)]
    amt_paise = int(amt_inr * 100)

    if category == "SOFT":
        reason = SOFT_ERROR_REASONS[(index - 1) % len(SOFT_ERROR_REASONS)]
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
                        "error_description": f"Payment debit declined: {reason}",
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
            "webhook_payload": payload
        }

    elif category == "RISK":
        reason = RISK_ERROR_REASONS[(index - 1) % len(RISK_ERROR_REASONS)]
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
                        "error_description": f"Security risk block: {reason}",
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
            "webhook_payload": payload
        }

    else:  # HARD
        reason = HARD_ERROR_REASONS[(index - 1) % len(HARD_ERROR_REASONS)]
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
                        "error_description": f"Permanent decline: {reason}",
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
