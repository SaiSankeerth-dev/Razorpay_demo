"""
Unit tests for the Deterministic Policy Engine.
Tests action decisions, progressive backoff schedules, and audit reasoning across buckets.
"""
import pytest
from agent.models import (
    DeclineBucket,
    DecidedAction,
    SubscriptionLifecycleState,
    ClassificationResult,
    ExtractedFailureData
)
from agent.policy_engine import PolicyEngine, RETRY_BACKOFF_SCHEDULE


def create_dummy_extracted_data(subscription_id="sub_test_pol_001"):
    return ExtractedFailureData(
        event_type="payment.failed",
        subscription_id=subscription_id,
        payment_id="pay_test_001",
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds"
    )


def test_policy_soft_decline_attempt_1():
    classification = ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="error_reason",
        matched_rule="Matched soft decline: insufficient_funds",
        reasoning="Insufficient funds detected"
    )
    extracted = create_dummy_extracted_data("sub_soft_01")

    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=0
    )

    assert decision.action == DecidedAction.SCHEDULE_RETRY
    assert decision.attempt_number == 1
    assert decision.retry_delay_seconds == 3600  # 1 hour
    assert decision.lifecycle_state == SubscriptionLifecycleState.ACTIVE_RECOVERY
    assert decision.is_terminal is False
    assert len(decision.reasoning) > 0
    assert "1/3" in decision.reasoning or "attempt #1" in decision.reasoning.lower()


def test_policy_soft_decline_attempt_2():
    classification = ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="error_reason",
        matched_rule="Matched soft decline",
        reasoning="Transient bank error"
    )
    extracted = create_dummy_extracted_data("sub_soft_02")

    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=1  # 1 prior attempt
    )

    assert decision.action == DecidedAction.SCHEDULE_RETRY
    assert decision.attempt_number == 2
    assert decision.retry_delay_seconds == 21600  # 6 hours
    assert decision.lifecycle_state == SubscriptionLifecycleState.ACTIVE_RECOVERY
    assert decision.is_terminal is False


def test_policy_soft_decline_attempt_3():
    classification = ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="error_reason",
        matched_rule="Matched soft decline",
        reasoning="Transient bank error"
    )
    extracted = create_dummy_extracted_data("sub_soft_03")

    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=2  # 2 prior attempts
    )

    assert decision.action == DecidedAction.SCHEDULE_RETRY
    assert decision.attempt_number == 3
    assert decision.retry_delay_seconds == 86400  # 24 hours
    assert decision.lifecycle_state == SubscriptionLifecycleState.ACTIVE_RECOVERY
    assert decision.is_terminal is False


def test_policy_hard_decline_nudge():
    classification = ClassificationResult(
        bucket=DeclineBucket.HARD_DECLINE,
        matched_field="error_reason",
        matched_rule="Matched hard decline: expired_card",
        reasoning="Expired card detected"
    )
    extracted = create_dummy_extracted_data("sub_hard_01")

    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=0
    )

    assert decision.action == DecidedAction.NUDGE_PAYMENT_UPDATE
    assert decision.retry_delay_seconds is None
    assert decision.lifecycle_state == SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE
    assert "Permanent credential" in decision.reasoning or "payment method update" in decision.reasoning.lower()


def test_policy_risk_flag_escalation():
    classification = ClassificationResult(
        bucket=DeclineBucket.RISK_FLAG,
        matched_field="error_reason",
        matched_rule="Matched risk: payment_risk_check_failed",
        reasoning="Issuer risk check failed"
    )
    extracted = create_dummy_extracted_data("sub_risk_01")

    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=0
    )

    assert decision.action == DecidedAction.ESCALATE_TO_HUMAN
    assert decision.retry_delay_seconds is None
    assert decision.lifecycle_state == SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
    assert decision.is_terminal is True
    assert "manual compliance and fraud review" in decision.reasoning.lower() or "human" in decision.reasoning.lower()
