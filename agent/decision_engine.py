"""
Recovery Decision Engine Orchestrator.

Integrates:
1. Webhook Failure Extraction
2. 3-Tier Error Taxonomy Classification
3. AI Diagnostician (Root Cause, Empirical P(rec), Recommended Action & Timing)
4. Deterministic Policy Firewall (Risk Checks, Retry Budget, DND, Opt-Out, Stopping Rules)
5. State Tracking & Continuous Financial Audit Logging
"""
import logging
from typing import Dict, Any, Tuple, Optional
from agent.models import (
    DeclineBucket,
    DecidedAction,
    SubscriptionLifecycleState,
    ClassificationResult,
    PolicyDecision,
    AuditLogEntry,
    ExtractedFailureData,
    AIDiagnosisResult,
    PolicyFirewallDecision
)
from agent.classifier import extract_failure_data, classify_decline
from agent.ai.diagnostician import AIDiagnostician
from agent.ai.provider import get_ai_provider
from agent.policy_firewall import PolicyFirewall
from agent.policy_engine import PolicyEngine
from db.repository import (
    get_subscription_recovery_state,
    upsert_subscription_recovery_state,
    save_recovery_audit_log
)

logger = logging.getLogger(__name__)


def process_webhook_decision(
    webhook_payload: Dict[str, Any],
    ai_provider: Optional[str] = None
) -> Tuple[ExtractedFailureData, ClassificationResult, PolicyDecision, Dict[str, Any]]:
    """
    Processes an incoming failure webhook:
    1. Extracts failure metadata
    2. Classifies decline bucket (SOFT_DECLINE, HARD_DECLINE, RISK_FLAG)
    3. Runs AI Diagnostician to assess cause, P(recovery), and recommended strategy
    4. Evaluates Deterministic Policy Firewall to authorize or override AI recommendation
    5. Updates subscription recovery state
    6. Persists continuous audit trail row in recovery_audit_log

    Returns:
        Tuple of (ExtractedFailureData, ClassificationResult, PolicyDecision, AuditRecordDict)
    """
    # 1. Extract failure data
    extracted = extract_failure_data(webhook_payload)
    sub_id = extracted.subscription_id or "unknown_sub"

    # 2. Classify decline
    classification = classify_decline(extracted)
    logger.info(
        f"[CLASSIFIER] Subscription '{sub_id}' -> Bucket: {classification.bucket.value} "
        f"(Rule: {classification.matched_rule})"
    )

    # 3. Retrieve current state for this subscription
    existing_state = get_subscription_recovery_state(sub_id) or {}
    prev_attempt_count = existing_state.get("current_attempt_count", 0)
    is_terminal = existing_state.get("is_terminal", False)
    prev_status_str = existing_state.get("status")
    prev_lifecycle_state = None
    if prev_status_str:
        try:
            prev_lifecycle_state = SubscriptionLifecycleState(prev_status_str)
        except ValueError:
            prev_lifecycle_state = None

    # 4. AI Diagnosis Layer
    diagnostician = AIDiagnostician(provider=get_ai_provider(ai_provider))
    ai_diagnosis: AIDiagnosisResult = diagnostician.diagnose_failure(
        failure_data=extracted,
        context={"current_attempt_count": prev_attempt_count, "is_terminal": is_terminal}
    )

    # 5. Deterministic Policy Firewall Authorization Layer
    firewall_decision: PolicyFirewallDecision = PolicyFirewall.evaluate(
        ai_recommendation=ai_diagnosis,
        classification=classification,
        failure_data=extracted,
        current_attempt_count=prev_attempt_count,
        is_already_terminal=is_terminal,
        current_lifecycle_state=prev_lifecycle_state
    )

    # Calculate attempt count tracking
    if firewall_decision.authorized_action == DecidedAction.SCHEDULE_RETRY:
        attempt_number = prev_attempt_count + 1
    else:
        attempt_number = prev_attempt_count

    # Build standardized PolicyDecision
    decision = PolicyDecision(
        action=firewall_decision.authorized_action,
        bucket=classification.bucket,
        subscription_id=sub_id,
        attempt_number=attempt_number,
        retry_delay_seconds=firewall_decision.effective_delay_seconds if firewall_decision.authorized_action == DecidedAction.SCHEDULE_RETRY else None,
        lifecycle_state=firewall_decision.lifecycle_state,
        is_terminal=firewall_decision.is_terminal,
        reasoning=firewall_decision.override_reason or ai_diagnosis.reasoning,
        policy_rule_id=firewall_decision.policy_rule_id
    )

    logger.info(
        f"[POLICY FIREWALL] Subscription '{sub_id}' -> Authorized Action: {decision.action.value} "
        f"(Override: {firewall_decision.override_applied}, Rule: {firewall_decision.policy_rule_id})"
    )

    # 6. Update subscription recovery state in DB
    updated_state_data = {
        "subscription_id": sub_id,
        "current_attempt_count": decision.attempt_number,
        "status": decision.lifecycle_state.value,
        "last_event_id": extracted.event_id,
        "last_payment_id": extracted.payment_id,
        "last_bucket": decision.bucket.value,
        "last_action": decision.action.value,
        "is_terminal": decision.is_terminal
    }
    upsert_subscription_recovery_state(updated_state_data)

    # 7. Record immutable decision in recovery_audit_log ONLY if a new decision was made
    saved_audit_row = {}
    if decision.action != DecidedAction.NO_ACTION_ALREADY_STOPPED:
        audit_entry = AuditLogEntry(
            event_id=extracted.event_id,
            subscription_id=sub_id,
            payment_id=extracted.payment_id,
            decline_bucket=decision.bucket.value,
            reasoning=decision.reasoning,
            decided_action=decision.action.value,
            attempt_number=decision.attempt_number,
            retry_delay_seconds=decision.retry_delay_seconds,
            subscription_lifecycle_state=decision.lifecycle_state.value,
            # AI & Policy Firewall tracking
            ai_diagnosis=ai_diagnosis.failure_diagnosis,
            ai_confidence=ai_diagnosis.confidence,
            ai_recommendation=ai_diagnosis.recommended_action.value,
            ai_provider=ai_diagnosis.provider_used,
            policy_decision=decision.action.value,
            policy_reason=decision.reasoning,
            policy_rule_id=decision.policy_rule_id,
            policy_override_applied=firewall_decision.override_applied,
            policy_override_reason=firewall_decision.override_reason
        )
        saved_audit_row = save_recovery_audit_log(audit_entry)
    else:
        logger.info(
            f"[REPLAY IGNORED] Subscription '{sub_id}' is already terminal. Skipped inserting new recovery_audit_log row."
        )

    return extracted, classification, decision, saved_audit_row

