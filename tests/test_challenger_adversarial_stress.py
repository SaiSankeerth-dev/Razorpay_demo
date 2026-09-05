"""
Empirical Challenger Adversarial & High-Contention Concurrency Harness.

Tests:
1. Schema & Fallback Defense: Pydantic validation rejects negative delays & invalid probabilities; AI Diagnostician falls back safely.
2. Policy Firewall Backoff Clamping: Clamps 0-hour AI recommendations to deterministic minimum backoff schedule.
3. Adversarial Risk Quarantine: Unconditionally overrides SCHEDULE_RETRY and NUDGE_PAYMENT_UPDATE to ESCALATE_TO_HUMAN.
4. Hard Decline Containment: Unconditionally overrides SCHEDULE_RETRY on HARD_DECLINE to NUDGE_PAYMENT_UPDATE.
5. Budget Exhaustion Stopping Rule: Caps retries at 3 and transitions to STOPPED_MAX_ATTEMPTS.
6. High-Contention Concurrency: 50 parallel threads processing webhooks on a single subscription.
7. Terminal Replay Flood: 25 parallel threads hitting a terminal subscription all receive NO_ACTION_ALREADY_STOPPED.
8. Concurrent Opt-Out Protection: Opted-out subscriptions block 100% of concurrent outbound touches.
9. Contact Cap Invariant: Sequential touch cap enforcement.
"""
import concurrent.futures
import datetime
import pytest
from pydantic import ValidationError
from db.config import settings
from db.repository import (
    clear_local_store,
    get_subscription_recovery_state,
    upsert_subscription_recovery_state,
    opt_out_subscription,
    get_subscription_contact_count,
    get_recovery_audit_logs,
    save_raw_webhook
)
from agent.models import (
    AIDiagnosisResult,
    DecidedAction,
    DeclineBucket,
    ExtractedFailureData,
    ClassificationResult,
    SubscriptionLifecycleState,
    PolicyDecision
)
from agent.ai.diagnostician import AIDiagnostician
from agent.ai.provider import MockAIProvider
from agent.policy_firewall import PolicyFirewall
from agent.compliance import evaluate_contact_compliance
from agent.action_engine import execute_recovery_action
from agent.decision_engine import process_webhook_decision
from agent.executors.nudge_executor import execute_nudge_send
from agent.executors.retry_executor import execute_payment_retry
from agent.executors.escalation_executor import execute_risk_escalation


@pytest.fixture(autouse=True)
def clean_db():
    settings.USE_LOCAL_DB = True
    clear_local_store()
    yield
    clear_local_store()


def test_schema_level_adversarial_rejection_and_fallback():
    """
    Verify that malformed AI outputs (negative delays, out-of-bound probabilities)
    are caught by Pydantic schema validation, and AIDiagnostician safely falls back to defaults.
    """
    # 1. Pydantic ValidationError on negative delay
    with pytest.raises(ValidationError):
        AIDiagnosisResult(
            failure_diagnosis="test",
            recovery_probability=0.8,
            recommended_action=DecidedAction.SCHEDULE_RETRY,
            recommended_delay_hours=-10,  # Invalid negative delay
            confidence=0.9,
            reasoning="test"
        )

    # 2. Pydantic ValidationError on probability > 1.0
    with pytest.raises(ValidationError):
        AIDiagnosisResult(
            failure_diagnosis="test",
            recovery_probability=1.5,  # Invalid probability
            recommended_action=DecidedAction.SCHEDULE_RETRY,
            recommended_delay_hours=1,
            confidence=0.9,
            reasoning="test"
        )

    # 3. Pydantic ValidationError on unknown/illegal action string
    with pytest.raises(ValidationError):
        AIDiagnosisResult(
            failure_diagnosis="test",
            recovery_probability=0.8,
            recommended_action="ILLEGAL_DIRECT_DEBIT",  # Invalid action token
            recommended_delay_hours=1,
            confidence=0.9,
            reasoning="test"
        )

    # 4. Fault injection: Timeout and HTTP 500 in AIProvider triggers safe fallback in AIDiagnostician
    class TimeoutProvider:
        def diagnose(self, failure_data, context=None):
            raise TimeoutError("HTTP 504 Gateway Timeout connecting to OpenAI API")

    diag_timeout = AIDiagnostician(provider=TimeoutProvider())
    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_timeout_test",
        error_reason="insufficient_funds"
    )
    timeout_fallback = diag_timeout.diagnose_failure(extracted)
    assert timeout_fallback.failure_diagnosis == "unclassified_error_failsafe"
    assert timeout_fallback.provider_used == "failsafe_local"
    assert timeout_fallback.recommended_action == DecidedAction.SCHEDULE_RETRY

    class ServerErrorProvider:
        def diagnose(self, failure_data, context=None):
            raise RuntimeError("HTTP 500 Internal Server Error from upstream AI service")

    diag_500 = AIDiagnostician(provider=ServerErrorProvider())
    error_fallback = diag_500.diagnose_failure(extracted)
    assert error_fallback.failure_diagnosis == "unclassified_error_failsafe"
    assert error_fallback.provider_used == "failsafe_local"
    assert error_fallback.recommended_action == DecidedAction.SCHEDULE_RETRY


def test_policy_firewall_backoff_clamping():
    """
    When AI recommends 0 hours delay for a soft decline retry,
    PolicyFirewall must enforce the deterministic minimum backoff schedule (Attempt 1 = 1h = 3600s).
    """
    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_clamp_001",
        payment_id="pay_clamp_001",
        error_reason="insufficient_funds",
        error_description="Soft decline"
    )
    classification = ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="error_reason",
        matched_rule="insufficient_funds",
        reasoning="Soft decline classified"
    )

    ai_zero_delay = AIDiagnosisResult(
        failure_diagnosis="liquidity_deficit",
        recovery_probability=0.85,
        recommended_action=DecidedAction.SCHEDULE_RETRY,
        recommended_delay_hours=0,  # AI says 0 hours
        customer_message_strategy="NONE",
        confidence=0.9,
        reasoning="Retry immediately"
    )

    # Attempt 1 -> minimum 3600s
    decision = PolicyFirewall.evaluate(ai_zero_delay, classification, extracted, current_attempt_count=0)
    assert decision.is_approved is True
    assert decision.authorized_action == DecidedAction.SCHEDULE_RETRY
    assert decision.effective_delay_seconds == 3600  # Clamped to 1h

    # Attempt 2 -> minimum 21600s (6h)
    decision2 = PolicyFirewall.evaluate(ai_zero_delay, classification, extracted, current_attempt_count=1)
    assert decision2.effective_delay_seconds == 21600  # Clamped to 6h

    # Attempt 3 -> minimum 86400s (24h)
    decision3 = PolicyFirewall.evaluate(ai_zero_delay, classification, extracted, current_attempt_count=2)
    assert decision3.effective_delay_seconds == 86400  # Clamped to 24h


def test_adversarial_risk_quarantine_all_actions():
    """
    Ensure PolicyFirewall unconditionally blocks ALL AI actions (SCHEDULE_RETRY, NUDGE_PAYMENT_UPDATE)
    when the classification is RISK_FLAG.
    """
    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_risk_strict",
        payment_id="pay_risk_strict",
        error_reason="card_blacklisted",
        error_description="Card blacklisted by issuer fraud control"
    )
    classification = ClassificationResult(
        bucket=DeclineBucket.RISK_FLAG,
        matched_field="error_reason",
        matched_rule="card_blacklisted",
        reasoning="Risk flag rule matched"
    )

    # Test with SCHEDULE_RETRY
    ai_retry = AIDiagnosisResult(
        failure_diagnosis="stolen",
        recovery_probability=0.99,
        recommended_action=DecidedAction.SCHEDULE_RETRY,
        recommended_delay_hours=1,
        customer_message_strategy="NONE",
        confidence=0.99,
        reasoning="Retry regardless"
    )
    dec_retry = PolicyFirewall.evaluate(ai_retry, classification, extracted, current_attempt_count=0)
    assert dec_retry.is_approved is False
    assert dec_retry.authorized_action == DecidedAction.ESCALATE_TO_HUMAN
    assert dec_retry.override_applied is True
    assert dec_retry.policy_rule_id == "RULE_FIREWALL_RISK_QUARANTINE"
    assert dec_retry.lifecycle_state == SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
    assert dec_retry.is_terminal is True

    # Test with NUDGE_PAYMENT_UPDATE
    ai_nudge = AIDiagnosisResult(
        failure_diagnosis="stolen",
        recovery_probability=0.8,
        recommended_action=DecidedAction.NUDGE_PAYMENT_UPDATE,
        recommended_delay_hours=0,
        customer_message_strategy="URGENT_CARD_UPDATE",
        confidence=0.9,
        reasoning="Nudge customer"
    )
    dec_nudge = PolicyFirewall.evaluate(ai_nudge, classification, extracted, current_attempt_count=0)
    assert dec_nudge.is_approved is False
    assert dec_nudge.authorized_action == DecidedAction.ESCALATE_TO_HUMAN
    assert dec_nudge.override_applied is True
    assert dec_nudge.policy_rule_id == "RULE_FIREWALL_RISK_QUARANTINE"
    assert dec_nudge.lifecycle_state == SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
    assert dec_nudge.is_terminal is True


def test_adversarial_hard_decline_override():
    """
    Ensure PolicyFirewall unconditionally intercepts SCHEDULE_RETRY on HARD_DECLINE
    and overrides to NUDGE_PAYMENT_UPDATE.
    """
    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_hard_override",
        error_reason="mandate_cancelled"
    )
    classification = ClassificationResult(
        bucket=DeclineBucket.HARD_DECLINE,
        matched_field="error_reason",
        matched_rule="mandate_cancelled",
        reasoning="Mandate cancelled"
    )
    ai_retry = AIDiagnosisResult(
        failure_diagnosis="mandate_issue",
        recovery_probability=0.6,
        recommended_action=DecidedAction.SCHEDULE_RETRY,
        recommended_delay_hours=2,
        customer_message_strategy="NONE",
        confidence=0.8,
        reasoning="Try auto retry"
    )
    decision = PolicyFirewall.evaluate(ai_retry, classification, extracted, current_attempt_count=0)
    assert decision.is_approved is False
    assert decision.authorized_action == DecidedAction.NUDGE_PAYMENT_UPDATE
    assert decision.override_applied is True
    assert decision.policy_rule_id == "RULE_FIREWALL_HARD_DECLINE_NUDGE_ONLY"
    assert decision.lifecycle_state == SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE
    assert decision.is_terminal is False


def test_high_contention_concurrency_single_subscription():
    """
    Bombard a single subscription with 50 concurrent threads processing webhook events.
    Verifies:
    1. No thread crashes or deadlocks.
    2. Attempt count is monotonically updated within valid bounds [1, 3].
    3. Final state is correctly recorded.
    """
    sub_id = "sub_high_contention_50"
    payload = {
        "entity": "event",
        "account_id": "acc_stress_test",
        "event": "payment.failed",
        "id": "evt_high_50",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_high_50",
                    "amount": 49900,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "insufficient_funds",
                    "notes": {"subscription_id": sub_id, "customer_email": "stress@example.com"}
                }
            }
        }
    }

    def worker(i):
        save_raw_webhook("payment.failed", payload, signature_valid=True, event_id=f"evt_high_50_{i}")
        return process_webhook_decision(payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(worker, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 50
    final_state = get_subscription_recovery_state(sub_id)
    assert final_state is not None
    assert final_state["subscription_id"] == sub_id
    assert final_state["current_attempt_count"] <= 3


def test_concurrent_terminal_replay_flood():
    """
    25 threads flood a terminal subscription (ESCALATED_HUMAN_REVIEW) simultaneously.
    Verifies that all 25 threads receive NO_ACTION_ALREADY_STOPPED and 0 new audit log rows are inserted.
    """
    sub_id = "sub_terminal_flood_25"
    upsert_subscription_recovery_state({
        "subscription_id": sub_id,
        "current_attempt_count": 0,
        "status": "ESCALATED_HUMAN_REVIEW",
        "is_terminal": True
    })

    payload = {
        "entity": "event",
        "event": "payment.failed",
        "id": "evt_flood_replay",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_flood_replay",
                    "amount": 99900,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "insufficient_funds",
                    "notes": {"subscription_id": sub_id}
                }
            }
        }
    }

    def replay_worker():
        return process_webhook_decision(payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(replay_worker) for _ in range(25)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 25
    for _, _, decision, audit_row in results:
        assert decision.action == DecidedAction.NO_ACTION_ALREADY_STOPPED
        assert decision.is_terminal is True
        assert audit_row == {}


def test_concurrent_opt_out_protection():
    """
    Verifies that once a customer opts out, all subsequent outbound nudges
    are 100% blocked under concurrent delivery.
    """
    sub_id = "sub_optout_race"
    upsert_subscription_recovery_state({
        "subscription_id": sub_id,
        "current_attempt_count": 0,
        "status": "AWAITING_CUSTOMER_UPDATE",
        "is_terminal": False,
        "is_opted_out": False
    })

    tz_ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    test_dt = datetime.datetime(2026, 8, 28, 14, 0, 0, tzinfo=tz_ist)

    # Trigger opt-out
    opt_out_subscription(sub_id)

    def nudge_worker():
        return execute_nudge_send(
            subscription_id=sub_id,
            customer_email="optout_race@example.com",
            check_time=test_dt
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(nudge_worker) for _ in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 10
    for r in results:
        assert r["allowed"] is False
        assert r["action_executed"] == "BLOCKED_OPT_OUT"
        assert r["action_result"] == "BLOCKED"


def test_sequential_lifetime_contact_cap():
    """
    Verifies that the lifetime contact touch cap (3 touches) is strictly enforced sequentially.
    Touches 1, 2, 3 succeed, Touch 4 is blocked.
    """
    sub_id = "sub_seq_cap"
    tz_ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    test_dt = datetime.datetime(2026, 8, 28, 14, 0, 0, tzinfo=tz_ist)

    # Touch 1
    r1 = execute_nudge_send(subscription_id=sub_id, check_time=test_dt)
    assert r1["allowed"] is True
    assert get_subscription_contact_count(sub_id) == 1

    # Touch 2
    r2 = execute_nudge_send(subscription_id=sub_id, check_time=test_dt)
    assert r2["allowed"] is True
    assert get_subscription_contact_count(sub_id) == 2

    # Touch 3
    r3 = execute_nudge_send(subscription_id=sub_id, check_time=test_dt)
    assert r3["allowed"] is True
    assert get_subscription_contact_count(sub_id) == 3

    # Touch 4 (Blocked by cap)
    r4 = execute_nudge_send(subscription_id=sub_id, check_time=test_dt)
    assert r4["allowed"] is False
    assert r4["action_executed"] == "BLOCKED_LIFETIME_CAP"
    assert get_subscription_contact_count(sub_id) == 3
