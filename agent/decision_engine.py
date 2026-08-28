"""
Recovery Decision Engine Orchestrator.

Integrates Classification, Policy Evaluation, State Tracking, and Audit Logging.
Takes a raw webhook payload (or webhook_events record) and deterministically executes Phase 2
decision-making without triggering external mutations.
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
    ExtractedFailureData
)
from agent.classifier import extract_failure_data, classify_decline
from agent.policy_engine import PolicyEngine
from db.repository import (
    get_subscription_recovery_state,
    upsert_subscription_recovery_state,
    save_recovery_audit_log
)

logger = logging.getLogger(__name__)


def process_webhook_decision(webhook_payload: Dict[str, Any]) -> Tuple[ExtractedFailureData, ClassificationResult, PolicyDecision, Dict[str, Any]]:
    """
    Processes an incoming failure webhook:
    1. Extracts failure metadata
    2. Classifies decline bucket (SOFT_DECLINE, HARD_DECLINE, RISK_FLAG)
    3. Fetches existing subscription state
    4. Evaluates deterministic policy engine
    5. Updates subscription recovery state
    6. Persists audit trail row in recovery_audit_log

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

    # 4. Evaluate Policy Engine
    decision = PolicyEngine.evaluate(
        classification=classification,
        extracted_data=extracted,
        current_attempt_count=prev_attempt_count,
        is_already_terminal=is_terminal,
        current_lifecycle_state=prev_lifecycle_state
    )

    logger.info(
        f"[POLICY DECISION] Subscription '{sub_id}' -> Action: {decision.action.value} "
        f"(Attempt: {decision.attempt_number}, State: {decision.lifecycle_state.value})"
    )

    # 5. Update subscription recovery state in DB
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

    # 6. Record immutable decision in recovery_audit_log
    audit_entry = AuditLogEntry(
        event_id=extracted.event_id,
        subscription_id=sub_id,
        payment_id=extracted.payment_id,
        decline_bucket=decision.bucket.value,
        reasoning=decision.reasoning,
        decided_action=decision.action.value,
        attempt_number=decision.attempt_number,
        retry_delay_seconds=decision.retry_delay_seconds,
        subscription_lifecycle_state=decision.lifecycle_state.value
    )
    saved_audit_row = save_recovery_audit_log(audit_entry)

    return extracted, classification, decision, saved_audit_row
