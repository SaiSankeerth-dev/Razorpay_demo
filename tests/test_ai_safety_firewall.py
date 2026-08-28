"""
Adversarial AI Safety & Policy Firewall Interception Tests.

Verifies that the Deterministic Policy Firewall unconditionally intercepts and overrides
hallucinated, unsafe, or malformed AI recommendations before any financial action executes.
"""
import pytest
from db.config import settings
from db.repository import clear_local_store, opt_out_subscription, upsert_subscription_recovery_state
from agent.models import (
    AIDiagnosisResult,
    DecidedAction,
    DeclineBucket,
    ExtractedFailureData,
    ClassificationResult,
    SubscriptionLifecycleState
)
from agent.ai.provider import MockAIProvider
from agent.policy_firewall import PolicyFirewall
from agent.decision_engine import process_webhook_decision


@pytest.fixture(autouse=True)
def clean_db():
    settings.USE_LOCAL_DB = True
    clear_local_store()
    yield
    clear_local_store()


def test_adversarial_case1_ai_recommends_retry_on_risk_decline():
    """
    ADVERSARIAL SAFETY TEST 1:
    AI hallucinates 'SCHEDULE_RETRY' on a card_blacklisted / stolen card decline.
    EXPECTED: Policy Firewall unconditionally overrides to 'ESCALATE_TO_HUMAN',
              blocks all debit attempts, and records override rationale.
    """
    payload = {
        "entity": "event",
        "event": "payment.failed",
        "id": "evt_adv_001",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_adv_001",
                    "amount": 499900,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "stolen_card",
                    "error_description": "Card reported stolen",
                    "notes": {"subscription_id": "sub_adv_001"}
                }
            }
        }
    }

    # Inject hallucinated AI diagnosis
    unsafe_ai = AIDiagnosisResult(
        failure_diagnosis="hallucinated_transient_failure",
        recovery_probability=0.99,
        recommended_action=DecidedAction.SCHEDULE_RETRY,
        recommended_delay_hours=1,
        customer_message_strategy="NONE",
        confidence=0.99,
        reasoning="Model hallucination: Looks like a temporary glitch.",
        provider_used="adversarial_test"
    )

    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_adv_001",
        payment_id="pay_adv_001",
        error_reason="stolen_card",
        error_description="Card reported stolen"
    )
    classification = ClassificationResult(
        bucket=DeclineBucket.RISK_FLAG,
        matched_field="error_reason",
        matched_rule="stolen_card",
        reasoning="Risk flag triggered"
    )

    firewall_decision = PolicyFirewall.evaluate(
        ai_recommendation=unsafe_ai,
        classification=classification,
        failure_data=extracted,
        current_attempt_count=0
    )

    assert firewall_decision.is_approved is False
    assert firewall_decision.authorized_action == DecidedAction.ESCALATE_TO_HUMAN
    assert firewall_decision.override_applied is True
    assert "Security / Risk quarantine" in firewall_decision.override_reason
    assert firewall_decision.lifecycle_state == SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
    assert firewall_decision.is_terminal is True


def test_adversarial_case2_ai_recommends_nudge_on_opted_out_customer():
    """
    ADVERSARIAL SAFETY TEST 2:
    AI recommends sending customer email nudge, but customer has explicitly opted out.
    EXPECTED: Compliance Guardrails & Action Executor unconditionally block outreach.
    """
    from agent.compliance import evaluate_contact_compliance
    from agent.action_engine import execute_recovery_action
    from agent.models import PolicyDecision

    sub_id = "sub_opted_out_002"
    opt_out_subscription(sub_id)

    # 1. Verify Compliance Guardrail evaluation
    compliance = evaluate_contact_compliance(sub_id)
    assert compliance.allowed is False
    assert compliance.guardrail == "OPT_OUT"

    # 2. Verify Action Executor blocks outreach
    dummy_decision = PolicyDecision(
        action=DecidedAction.NUDGE_PAYMENT_UPDATE,
        bucket=DeclineBucket.HARD_DECLINE,
        subscription_id=sub_id,
        attempt_number=0,
        lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE,
        is_terminal=False,
        reasoning="Send update link",
        policy_rule_id="RULE_TEST"
    )

    action_res = execute_recovery_action(decision=dummy_decision, customer_email="optout@example.com")
    assert action_res["action_executed"] == "BLOCKED_OPT_OUT"
    assert action_res["action_result"] == "BLOCKED"



def test_adversarial_case3_ai_recommends_retry_after_budget_exhaustion():
    """
    ADVERSARIAL SAFETY TEST 3:
    Subscription has already completed 3 retry attempts. AI recommends attempt #4.
    EXPECTED: Policy Firewall blocks attempt #4 and forces terminal state STOPPED_MAX_ATTEMPTS.
    """
    sub_id = "sub_budget_003"
    upsert_subscription_recovery_state({
        "subscription_id": sub_id,
        "current_attempt_count": 3,
        "status": "ACTIVE_RECOVERY",
        "is_terminal": False
    })

    ai_retry = AIDiagnosisResult(
        failure_diagnosis="temporary_liquidity_deficit",
        recovery_probability=0.80,
        recommended_action=DecidedAction.SCHEDULE_RETRY,
        recommended_delay_hours=1,
        customer_message_strategy="NONE",
        confidence=0.90,
        reasoning="Try one more time.",
        provider_used="test"
    )

    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id=sub_id,
        error_reason="insufficient_funds"
    )
    classification = ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="error_reason",
        matched_rule="insufficient_funds",
        reasoning="Soft decline"
    )

    firewall_decision = PolicyFirewall.evaluate(
        ai_recommendation=ai_retry,
        classification=classification,
        failure_data=extracted,
        current_attempt_count=3
    )

    assert firewall_decision.is_approved is False
    assert firewall_decision.authorized_action == DecidedAction.NUDGE_PAYMENT_UPDATE
    assert firewall_decision.override_applied is True
    assert "Automated retry limit reached" in firewall_decision.override_reason
    assert firewall_decision.is_terminal is True



def test_adversarial_case4_ai_recommends_retry_on_hard_decline():
    """
    ADVERSARIAL SAFETY TEST 4:
    Decline is HARD_DECLINE (expired card / revoked mandate), but AI erroneously recommended retry.
    EXPECTED: Policy Firewall overrides to NUDGE_PAYMENT_UPDATE (preventing useless bank retries).
    """
    ai_retry = AIDiagnosisResult(
        failure_diagnosis="card_expired",
        recovery_probability=0.50,
        recommended_action=DecidedAction.SCHEDULE_RETRY,
        recommended_delay_hours=1,
        customer_message_strategy="NONE",
        confidence=0.85,
        reasoning="Mistakenly recommended retry.",
        provider_used="test"
    )

    extracted = ExtractedFailureData(
        event_type="payment.failed",
        subscription_id="sub_hard_004",
        error_reason="expired_card"
    )
    classification = ClassificationResult(
        bucket=DeclineBucket.HARD_DECLINE,
        matched_field="error_reason",
        matched_rule="expired_card",
        reasoning="Hard decline"
    )

    firewall_decision = PolicyFirewall.evaluate(
        ai_recommendation=ai_retry,
        classification=classification,
        failure_data=extracted,
        current_attempt_count=0
    )

    assert firewall_decision.is_approved is False
    assert firewall_decision.authorized_action == DecidedAction.NUDGE_PAYMENT_UPDATE
    assert firewall_decision.override_applied is True
    assert "Permanent credential invalidation" in firewall_decision.override_reason
