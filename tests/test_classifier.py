"""
Unit tests for Decline Classifier using realistic Razorpay webhook payloads.
Tests all three canonical decline buckets: SOFT_DECLINE, HARD_DECLINE, RISK_FLAG.
"""
import pytest
from agent.models import DeclineBucket
from agent.classifier import extract_failure_data, classify_decline


# ============================================================================
# REALISTIC RAZORPAY WEBHOOK SAMPLE PAYLOADS
# ============================================================================

PAYLOAD_SOFT_DECLINE_INSUFFICIENT_FUNDS = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_soft_insufficient_001",
                "entity": "payment",
                "amount": 49900,
                "currency": "INR",
                "status": "failed",
                "order_id": "order_sample_001",
                "invoice_id": "inv_sample_001",
                "method": "card",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Payment failed due to insufficient funds in customer bank account",
                "error_source": "customer",
                "error_step": "payment_authorization",
                "error_reason": "insufficient_funds",
                "notes": {
                    "subscription_id": "sub_soft_test_101"
                }
            }
        }
    }
}

PAYLOAD_SOFT_DECLINE_GATEWAY_TIMEOUT = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_soft_gateway_002",
                "entity": "payment",
                "amount": 49900,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "error_code": "GATEWAY_ERROR",
                "error_description": "Bank network connection timed out during recurring processing",
                "error_source": "gateway",
                "error_step": "payment_authorization",
                "error_reason": "gateway_technical_error",
                "notes": {
                    "subscription_id": "sub_soft_test_102"
                }
            }
        }
    }
}

PAYLOAD_SOFT_DECLINE_SUBSCRIPTION_PENDING = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "subscription.pending",
    "contains": ["subscription"],
    "payload": {
        "subscription": {
            "entity": {
                "id": "sub_soft_pending_103",
                "entity": "subscription",
                "plan_id": "plan_sample_pro",
                "customer_id": "cust_sample_103",
                "status": "pending",
                "auth_attempts": 1,
                "total_count": 12,
                "paid_count": 0,
                "notes": {
                    "tier": "pro_monthly"
                }
            }
        }
    }
}

PAYLOAD_HARD_DECLINE_EXPIRED_CARD = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_hard_expired_201",
                "entity": "payment",
                "amount": 49900,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Card has expired (expiry date 05/24 in past)",
                "error_source": "customer",
                "error_step": "payment_authentication",
                "error_reason": "expired_card",
                "notes": {
                    "subscription_id": "sub_hard_test_201"
                }
            }
        }
    }
}

PAYLOAD_HARD_DECLINE_TOKEN_INELIGIBLE = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_hard_token_202",
                "entity": "payment",
                "amount": 49900,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Card token is deleted or ineligible for recurring autopay",
                "error_source": "business",
                "error_step": "payment_initiation",
                "error_reason": "token_not_eligible",
                "notes": {
                    "subscription_id": "sub_hard_test_202"
                }
            }
        }
    }
}

PAYLOAD_HARD_DECLINE_SUBSCRIPTION_HALTED = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "subscription.halted",
    "contains": ["subscription"],
    "payload": {
        "subscription": {
            "entity": {
                "id": "sub_hard_halted_203",
                "entity": "subscription",
                "plan_id": "plan_sample_pro",
                "status": "halted",
                "auth_attempts": 4,
                "notes": {}
            }
        }
    }
}

PAYLOAD_RISK_FLAG_SECURITY_CHECK = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_risk_security_301",
                "entity": "payment",
                "amount": 49900,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Transaction declined by card issuer risk check filters",
                "error_source": "gateway",
                "error_step": "payment_authorization",
                "error_reason": "payment_risk_check_failed",
                "notes": {
                    "subscription_id": "sub_risk_test_301"
                }
            }
        }
    }
}

PAYLOAD_RISK_FLAG_BLACKLISTED_CARD = {
    "entity": "event",
    "account_id": "acc_sample_merchant",
    "event": "payment.failed",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_risk_blacklist_302",
                "entity": "payment",
                "amount": 49900,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Card blacklisted by issuing bank due to suspected fraud",
                "error_source": "gateway",
                "error_step": "payment_authorization",
                "error_reason": "card_blacklisted",
                "notes": {
                    "subscription_id": "sub_risk_test_302"
                }
            }
        }
    }
}


# ============================================================================
# CLASSIFIER TESTS
# ============================================================================

def test_classify_soft_decline_insufficient_funds():
    extracted = extract_failure_data(PAYLOAD_SOFT_DECLINE_INSUFFICIENT_FUNDS)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.SOFT_DECLINE
    assert "insufficient_funds" in result.reasoning
    assert extracted.subscription_id == "sub_soft_test_101"


def test_classify_soft_decline_gateway_timeout():
    extracted = extract_failure_data(PAYLOAD_SOFT_DECLINE_GATEWAY_TIMEOUT)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.SOFT_DECLINE
    assert "gateway_technical_error" in result.matched_rule or "GATEWAY_ERROR" in result.matched_rule


def test_classify_soft_decline_subscription_pending():
    extracted = extract_failure_data(PAYLOAD_SOFT_DECLINE_SUBSCRIPTION_PENDING)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.SOFT_DECLINE
    assert "pending" in result.reasoning


def test_classify_hard_decline_expired_card():
    extracted = extract_failure_data(PAYLOAD_HARD_DECLINE_EXPIRED_CARD)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.HARD_DECLINE
    assert "expired_card" in result.reasoning


def test_classify_hard_decline_token_ineligible():
    extracted = extract_failure_data(PAYLOAD_HARD_DECLINE_TOKEN_INELIGIBLE)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.HARD_DECLINE
    assert "token_not_eligible" in result.reasoning


def test_classify_hard_decline_subscription_halted():
    extracted = extract_failure_data(PAYLOAD_HARD_DECLINE_SUBSCRIPTION_HALTED)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.HARD_DECLINE
    assert "halted" in result.reasoning


def test_classify_risk_flag_security_check():
    extracted = extract_failure_data(PAYLOAD_RISK_FLAG_SECURITY_CHECK)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.RISK_FLAG
    assert "payment_risk_check_failed" in result.reasoning
    assert "human" in result.reasoning.lower()


def test_classify_risk_flag_blacklisted_card():
    extracted = extract_failure_data(PAYLOAD_RISK_FLAG_BLACKLISTED_CARD)
    result = classify_decline(extracted)
    assert result.bucket == DeclineBucket.RISK_FLAG
    assert "card_blacklisted" in result.reasoning
