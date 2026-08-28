"""
Tests for Compliance Guardrails (Hard-coded safety rules).

Verifies:
1. DND Window: No nudge sent outside 9am-8pm IST; held with next window timestamp.
2. Opt-Out: Customer opt-out strictly blocks all future nudges.
3. Lifetime Contact Cap: No more than MAX_LIFETIME_CONTACT_ATTEMPTS touches across subscription lifecycle.
"""
import pytest
import datetime
from agent.compliance import check_dnd_window, evaluate_contact_compliance
from agent.executors.nudge_executor import execute_nudge_send
from db.repository import (
    clear_local_store,
    opt_out_subscription,
    is_subscription_opted_out,
    increment_subscription_contact_count,
    get_subscription_contact_count,
    save_recovery_audit_log,
    get_recovery_audit_logs
)
from agent.models import AuditLogEntry, DecidedAction, DeclineBucket, SubscriptionLifecycleState


@pytest.fixture(autouse=True)
def clean_db():
    clear_local_store()
    yield
    clear_local_store()


def test_dnd_window_blocks_and_reschedules_at_11pm():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that a nudge queued at 11:00 PM IST (outside 9am-8pm window) is held,
    not sent, and returns the rescheduled 9:00 AM timestamp.
    """
    sub_id = "sub_dnd_test_101"
    
    # 11:00 PM IST (23:00)
    dt_11pm = datetime.datetime(2026, 8, 28, 23, 0, 0)
    
    # 1. Evaluate compliance at 11:00 PM
    compliance = evaluate_contact_compliance(subscription_id=sub_id, check_time=dt_11pm)
    assert compliance.allowed is False
    assert compliance.guardrail == "DND"
    assert compliance.rescheduled_at is not None
    assert "09:00:00" in compliance.rescheduled_at  # Rescheduled to 9:00 AM next day

    # 2. Execute nudge send through executor at 11:00 PM
    audit_entry = AuditLogEntry(
        subscription_id=sub_id,
        decline_bucket=DeclineBucket.HARD_DECLINE.value,
        reasoning="Hard decline queued at 11pm",
        decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
        attempt_number=0,
        subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
    )
    saved_audit = save_recovery_audit_log(audit_entry)

    res = execute_nudge_send(
        subscription_id=sub_id,
        audit_log_id=saved_audit["id"],
        check_time=dt_11pm
    )

    assert res["allowed"] is False
    assert res["action_executed"] == "HOLD_DND"
    assert res["action_result"] == "HELD_DND"
    assert "09:00:00" in res["compliance_details"]["rescheduled_at"]

    # Verify audit log reflects held state
    logs = get_recovery_audit_logs(subscription_id=sub_id)
    assert logs[0]["action_executed"] == "HOLD_DND"
    assert logs[0]["action_result"] == "HELD_DND"


def test_opt_out_blocks_nudge_even_on_fresh_decline():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that if a subscription is flagged opted-out, no further nudges ever fire,
    even if a fresh HARD_DECLINE decision arrives.
    """
    sub_id = "sub_optout_test_202"
    
    # Step 1: Customer opts out
    opt_out_subscription(sub_id)
    assert is_subscription_opted_out(sub_id) is True

    # Step 2: Fresh decline arrives
    audit_entry = AuditLogEntry(
        subscription_id=sub_id,
        decline_bucket=DeclineBucket.HARD_DECLINE.value,
        reasoning="Fresh hard decline on opted-out subscription",
        decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
        attempt_number=0,
        subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
    )
    saved_audit = save_recovery_audit_log(audit_entry)

    # Force daytime so DND does not trigger
    dt_daytime = datetime.datetime(2026, 8, 28, 14, 0, 0)
    
    res = execute_nudge_send(
        subscription_id=sub_id,
        audit_log_id=saved_audit["id"],
        check_time=dt_daytime
    )

    assert res["allowed"] is False
    assert res["action_executed"] == "BLOCKED_OPT_OUT"
    assert res["action_result"] == "BLOCKED"
    assert "opted out" in res["compliance_details"]["reason"].lower()

    # Verify audit log reflects blocked state
    logs = get_recovery_audit_logs(subscription_id=sub_id)
    assert logs[0]["action_executed"] == "BLOCKED_OPT_OUT"
    assert logs[0]["action_result"] == "BLOCKED"


def test_lifetime_contact_cap_blocks_contact_n_plus_1():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that global lifetime contact cap (e.g. 3 touches) holds across multiple
    separate decline events, and contact #4 is strictly blocked.
    """
    sub_id = "sub_cap_test_303"
    dt_daytime = datetime.datetime(2026, 8, 28, 15, 0, 0)

    # Simulate 3 prior contact attempts across separate decline events
    for attempt in range(1, 4):
        audit = save_recovery_audit_log(AuditLogEntry(
            subscription_id=sub_id,
            decline_bucket=DeclineBucket.HARD_DECLINE.value,
            reasoning=f"Decline event #{attempt}",
            decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
            attempt_number=0,
            subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
        ))
        res = execute_nudge_send(subscription_id=sub_id, audit_log_id=audit["id"], check_time=dt_daytime)
        assert res["allowed"] is True

    assert get_subscription_contact_count(sub_id) == 3

    # Attempt #4 (Contact N+1) on a new decline event
    audit_4 = save_recovery_audit_log(AuditLogEntry(
        subscription_id=sub_id,
        decline_bucket=DeclineBucket.HARD_DECLINE.value,
        reasoning="Decline event #4 (exceeding lifetime cap)",
        decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
        attempt_number=0,
        subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
    ))
    res_4 = execute_nudge_send(subscription_id=sub_id, audit_log_id=audit_4["id"], check_time=dt_daytime)

    # Assert contact #4 was strictly blocked by lifetime cap
    assert res_4["allowed"] is False
    assert res_4["action_executed"] == "BLOCKED_LIFETIME_CAP"
    assert res_4["action_result"] == "BLOCKED"
    assert "lifetime contact cap" in res_4["compliance_details"]["reason"].lower()

    # Lifetime contact count remains capped at 3
    assert get_subscription_contact_count(sub_id) == 3
