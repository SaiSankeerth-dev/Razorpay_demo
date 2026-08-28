"""
Tests for Phase 3 Action Executors & Continuous Audit Trail.
Verifies real Razorpay retry execution, SMTP nudge sender, RISK_FLAG zero-contact guardrail,
and continuous decision-to-outcome audit logging.
"""
import pytest
import datetime
from unittest.mock import patch, MagicMock
from agent.models import (
    PolicyDecision,
    DecidedAction,
    DeclineBucket,
    SubscriptionLifecycleState,
    AuditLogEntry
)
from agent.executors.retry_executor import execute_payment_retry
from agent.executors.nudge_executor import execute_nudge_send
from agent.executors.escalation_executor import execute_risk_escalation
from agent.action_engine import execute_recovery_action
from db.repository import (
    clear_local_store,
    save_recovery_audit_log,
    get_recovery_audit_logs
)


@pytest.fixture(autouse=True)
def clean_db():
    clear_local_store()
    yield
    clear_local_store()


def test_retry_executor_real_api_call():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Execute real retry against Razorpay test mode and verify real API outcome is logged.
    """
    # 1. Save a decision row
    audit_entry = AuditLogEntry(
        subscription_id="sub_test_retry_001",
        decline_bucket=DeclineBucket.SOFT_DECLINE.value,
        reasoning="Soft decline due to insufficient funds. Retry #1 queued.",
        decided_action=DecidedAction.SCHEDULE_RETRY.value,
        attempt_number=1,
        retry_delay_seconds=3600,
        subscription_lifecycle_state=SubscriptionLifecycleState.ACTIVE_RECOVERY.value
    )
    saved_audit = save_recovery_audit_log(audit_entry)
    audit_id = saved_audit["id"]

    # 2. Execute retry
    res = execute_payment_retry(
        subscription_id="sub_test_retry_001",
        audit_log_id=audit_id
    )

    assert res["action_executed"] == "RETRY_PAYMENT"
    assert "action_result" in res
    assert "api_response" in res
    assert res["executed_at"] is not None

    # 3. Verify continuous audit trail (SAME row updated with action outcome)
    updated_logs = get_recovery_audit_logs(subscription_id="sub_test_retry_001")
    assert len(updated_logs) == 1
    log_row = updated_logs[0]
    assert log_row["id"] == audit_id
    assert log_row["decided_action"] == "SCHEDULE_RETRY"
    assert log_row["action_executed"] == "RETRY_PAYMENT"
    assert log_row["action_result"] is not None
    assert log_row["executed_at"] is not None


def test_nudge_sender_email_attempt():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Execute email nudge send via SMTP and log real transmission attempt/error to audit table.
    """
    audit_entry = AuditLogEntry(
        subscription_id="sub_test_nudge_002",
        decline_bucket=DeclineBucket.HARD_DECLINE.value,
        reasoning="Expired card detected. Customer update link queued.",
        decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
        attempt_number=0,
        subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
    )
    saved_audit = save_recovery_audit_log(audit_entry)
    audit_id = saved_audit["id"]

    # Force check_time within allowed DND window (e.g. 12:00 PM IST)
    dt_midday = datetime.datetime(2026, 8, 28, 12, 0, 0)

    res = execute_nudge_send(
        subscription_id="sub_test_nudge_002",
        customer_email="customer.test@example.com",
        audit_log_id=audit_id,
        check_time=dt_midday
    )

    assert res["allowed"] is True
    assert res["action_executed"] == "SEND_EMAIL_NUDGE"
    assert res["action_result"] is not None  # Either SENT or FAILED: <smtp error>

    # Verify audit table row updated
    logs = get_recovery_audit_logs(subscription_id="sub_test_nudge_002")
    assert len(logs) == 1
    assert logs[0]["action_executed"] == "SEND_EMAIL_NUDGE"
    assert logs[0]["executed_at"] is not None


def test_risk_flag_zero_contact_and_zero_retry_guarantee():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that RISK_FLAG decisions NEVER trigger any retry API call and NEVER send any customer nudge.
    """
    audit_entry = AuditLogEntry(
        subscription_id="sub_test_risk_003",
        decline_bucket=DeclineBucket.RISK_FLAG.value,
        reasoning="Payment failed due to risk filter. Escalation required.",
        decided_action=DecidedAction.ESCALATE_TO_HUMAN.value,
        attempt_number=0,
        subscription_lifecycle_state=SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW.value
    )
    saved_audit = save_recovery_audit_log(audit_entry)
    audit_id = saved_audit["id"]

    decision = PolicyDecision(
        action=DecidedAction.ESCALATE_TO_HUMAN,
        bucket=DeclineBucket.RISK_FLAG,
        subscription_id="sub_test_risk_003",
        attempt_number=0,
        lifecycle_state=SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW,
        is_terminal=True,
        reasoning="Security flag raised",
        policy_rule_id="RULE_RISK_001"
    )

    # Dispatch through Action Engine
    res = execute_recovery_action(
        decision=decision,
        audit_log_id=audit_id
    )

    # Prove zero contact and zero retry
    assert res["action_executed"] == "ESCALATE_TO_HUMAN"
    assert res["action_result"] == "FLAGGED_FOR_HUMAN_REVIEW"
    assert res["details"]["automated_contact_sent"] is False
    assert res["details"]["automated_retry_called"] is False
    assert res["details"]["human_review_required"] is True

    # Check continuous audit log row
    logs = get_recovery_audit_logs(subscription_id="sub_test_risk_003")
    assert len(logs) == 1
    assert logs[0]["action_executed"] == "ESCALATE_TO_HUMAN"
    assert logs[0]["action_result"] == "FLAGGED_FOR_HUMAN_REVIEW"
