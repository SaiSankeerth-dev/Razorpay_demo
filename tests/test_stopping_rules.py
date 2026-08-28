"""
Tests for Global Stopping Rules and Replay Webhook Idempotency.

Verifies:
1. Attempt #4 is strictly blocked when max retry limit (3) is reached.
2. A subscription marked terminal (DONE / STOPPED_MAX_ATTEMPTS / ESCALATED_HUMAN_REVIEW)
   CANNOT be reopened or re-triggered by a duplicate or replayed webhook.
"""
import pytest
from agent.models import (
    DeclineBucket,
    DecidedAction,
    SubscriptionLifecycleState,
    ClassificationResult,
    ExtractedFailureData
)
from agent.policy_engine import PolicyEngine
from agent.decision_engine import process_webhook_decision
from db.repository import clear_local_store, get_subscription_recovery_state, get_recovery_audit_logs
from tests.test_classifier import PAYLOAD_SOFT_DECLINE_INSUFFICIENT_FUNDS, PAYLOAD_RISK_FLAG_SECURITY_CHECK


@pytest.fixture(autouse=True)
def clean_db():
    clear_local_store()
    yield
    clear_local_store()


def test_stopping_rule_blocks_attempt_4():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that when a subscription has already reached 3 retry attempts,
    a 4th failure is blocked from auto-retrying and transitioned to STOPPED_MAX_ATTEMPTS.
    """
    classification = ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="error_reason",
        matched_rule="Matched soft decline: insufficient_funds",
        reasoning="Insufficient funds detected"
    )
    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_test_stopping_001",
        payment_id="pay_test_004",
        error_code="BAD_REQUEST_ERROR",
        error_reason="insufficient_funds"
    )

    # Prior attempts = 3 (Attempt #4 incoming)
    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=3,
        is_already_terminal=False
    )

    assert decision.action != DecidedAction.SCHEDULE_RETRY
    assert decision.attempt_number == 4
    assert decision.retry_delay_seconds is None
    assert decision.lifecycle_state == SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS
    assert decision.is_terminal is True
    assert "retry limit reached" in decision.reasoning.lower() or "stopping automated retries" in decision.reasoning.lower()


def test_replay_webhook_on_terminal_subscription_ignored():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that a duplicate / replayed webhook for an already-stopped (DONE)
    subscription returns NO_ACTION_ALREADY_STOPPED and does NOT increment attempt counts.
    """
    sub_id = "sub_terminal_replay_002"
    payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment.failed",
        "id": "evt_replay_001",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_replay_001",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "insufficient_funds",
                    "notes": {"subscription_id": sub_id}
                }
            }
        }
    }

    # Step 1: Simulate 3 failed attempts to push subscription to terminal state
    for i in range(1, 4):
        _, _, decision, _ = process_webhook_decision(payload)
        assert decision.action == DecidedAction.SCHEDULE_RETRY
        assert decision.attempt_number == i

    # 4th attempt: hits stopping rule -> marks terminal
    _, _, decision_4, _ = process_webhook_decision(payload)
    assert decision_4.lifecycle_state == SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS
    assert decision_4.is_terminal is True

    # Step 2: Now send a replayed / duplicate webhook
    _, _, decision_replay, audit_replay = process_webhook_decision(payload)

    # Step 3: Assert replay was blocked without re-triggering actions
    assert decision_replay.action == DecidedAction.NO_ACTION_ALREADY_STOPPED
    assert decision_replay.is_terminal is True
    assert "Global Stopping Rule" in decision_replay.reasoning
    assert "replayed webhook acknowledged without re-triggering" in decision_replay.reasoning.lower()

    # Confirm subscription state in DB did not advance attempt count past terminal state
    state = get_subscription_recovery_state(sub_id)
    assert state["is_terminal"] is True
    assert state["status"] == SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS.value

    # Confirm that NO new row was added to recovery_audit_log for the replayed event
    audit_logs = get_recovery_audit_logs(subscription_id=sub_id)
    assert len(audit_logs) == 4  # Exactly 4 rows from attempts 1, 2, 3, 4 (0 from replay)
    assert audit_replay == {}


def test_risk_escalated_subscription_cannot_be_reopened():
    """
    Prove that a subscription flagged as RISK_FLAG is marked terminal
    and cannot be reopened by subsequent soft-decline webhooks.
    """
    sub_id = "sub_risk_terminal_003"
    risk_payload = {
        "entity": "event",
        "id": "evt_risk_init_001",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_risk_001",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "payment_risk_check_failed",
                    "notes": {"subscription_id": sub_id}
                }
            }
        }
    }

    # Process risk event
    _, _, decision_risk, _ = process_webhook_decision(risk_payload)
    assert decision_risk.action == DecidedAction.ESCALATE_TO_HUMAN
    assert decision_risk.lifecycle_state == SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
    assert decision_risk.is_terminal is True

    # Replay or new payment failure on same subscription
    soft_payload = {
        "entity": "event",
        "id": "evt_subsequent_002",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_subsequent_002",
                    "status": "failed",
                    "error_code": "GATEWAY_ERROR",
                    "error_reason": "insufficient_funds",
                    "notes": {"subscription_id": sub_id}
                }
            }
        }
    }

    _, _, decision_subsequent, _ = process_webhook_decision(soft_payload)
    assert decision_subsequent.action == DecidedAction.NO_ACTION_ALREADY_STOPPED
    assert decision_subsequent.lifecycle_state == SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
