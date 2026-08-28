"""
Razorpay Decline Classification Engine.

Classifies incoming webhook failure payloads into exactly one of three canonical buckets:
1. SOFT_DECLINE: Transient issues (insufficient funds, gateway timeouts). Eligible for automated retry.
2. HARD_DECLINE: Permanent credential issues (expired card, deleted token, revoked mandate, halted subscription). Requires customer payment update.
3. RISK_FLAG: Security & compliance triggers (issuer risk check, card blacklisted, suspected fraud). Requires human escalation only.

Source of Truth: Razorpay Payment Failure Taxonomy & Error Codes.
"""
import logging
from typing import Dict, Any, Tuple
from agent.models import (
    DeclineBucket,
    ClassificationResult,
    ExtractedFailureData
)

logger = logging.getLogger(__name__)

# ============================================================================
# CANONICAL RAZORPAY ERROR CODE TAXONOMY MAPPINGS
# ============================================================================

RISK_FLAG_REASONS = {
    "payment_risk_check_failed",
    "risk_check_failed",
    "high_risk",
    "fraud_suspected",
    "card_blacklisted",
    "stolen_card",
    "lost_card",
    "restricted_card",
    "do_not_honor",
    "compliance_block",
    "security_violation",
    "velocity_exceeded_risk"
}

HARD_DECLINE_REASONS = {
    "expired_card",
    "invalid_card",
    "card_inactive",
    "token_not_eligible",
    "token_deleted",
    "token_inactive",
    "mandate_cancelled",
    "mandate_inactive",
    "mandate_not_found",
    "customer_mandate_revoked",
    "bank_account_invalid",
    "account_closed",
    "card_type_not_supported",
    "recurring_not_supported",
    "mandate_limit_exceeded_permanent"
}

SOFT_DECLINE_REASONS = {
    "insufficient_funds",
    "payment_failed",
    "gateway_error",
    "gateway_technical_error",
    "bank_technical_error",
    "payment_timed_out",
    "payment_processing_error",
    "transaction_frequency_limit_exceeded",
    "daily_limit_exceeded",
    "temporary_issuer_down",
    "network_error",
    "server_error",
    "issuer_unavailable",
    "bank_timeout",
    "otp_expired"
}


def extract_failure_data(webhook_payload: Dict[str, Any]) -> ExtractedFailureData:
    """
    Extracts and normalizes failure metadata from a raw Razorpay webhook payload.
    Supports payment.failed, subscription.pending, and subscription.halted events.
    """
    event_type = webhook_payload.get("event", "unknown")
    event_id = webhook_payload.get("id") or webhook_payload.get("event_id")

    payload_container = webhook_payload.get("payload", {})
    payment_entity = payload_container.get("payment", {}).get("entity", {})
    subscription_entity = payload_container.get("subscription", {}).get("entity", {})

    # Extract payment fields if present
    payment_id = payment_entity.get("id")
    error_code = payment_entity.get("error_code")
    error_description = payment_entity.get("error_description")
    error_source = payment_entity.get("error_source")
    error_step = payment_entity.get("error_step")
    error_reason = payment_entity.get("error_reason")

    # Extract subscription ID from payment notes or subscription entity
    subscription_id = (
        subscription_entity.get("id")
        or payment_entity.get("notes", {}).get("subscription_id")
        or payment_entity.get("subscription_id")
        or payment_entity.get("invoice_id")
    )
    subscription_status = subscription_entity.get("status")
    auth_attempts = subscription_entity.get("auth_attempts")

    return ExtractedFailureData(
        event_type=event_type,
        event_id=event_id,
        subscription_id=subscription_id,
        payment_id=payment_id,
        error_code=error_code,
        error_description=error_description,
        error_source=error_source,
        error_step=error_step,
        error_reason=error_reason,
        subscription_status=subscription_status,
        auth_attempts=auth_attempts,
        raw_entity=payment_entity or subscription_entity
    )


def classify_decline(data: ExtractedFailureData) -> ClassificationResult:
    """
    Classifies failure data into exactly one canonical DeclineBucket using deterministic rules.

    Evaluation Precedence:
    1. Check for Security/Fraud indicators (RISK_FLAG)
    2. Check for Permanent credential/mandate failures or Halted state (HARD_DECLINE)
    3. Check for Transient failure reasons or Pending state (SOFT_DECLINE)
    """
    reason_norm = (data.error_reason or "").strip().lower()
    code_norm = (data.error_code or "").strip().upper()
    desc_norm = (data.error_description or "").strip().lower()
    source_norm = (data.error_source or "").strip().lower()

    # ========================================================================
    # RULE 1: RISK_FLAG (Highest Priority — Safety & Anti-Fraud)
    # ========================================================================
    if reason_norm in RISK_FLAG_REASONS:
        return ClassificationResult(
            bucket=DeclineBucket.RISK_FLAG,
            matched_field="error_reason",
            matched_rule=f"Matched documented risk reason: '{reason_norm}'",
            reasoning=f"Transaction blocked by security/risk filter with reason '{reason_norm}'. Requires human compliance review; automated retry forbidden.",
            error_code=data.error_code,
            error_reason=data.error_reason
        )

    for keyword in ["risk", "fraud", "blacklisted", "stolen", "lost card", "security check", "compliance block", "do not honor"]:
        if keyword in desc_norm:
            return ClassificationResult(
                bucket=DeclineBucket.RISK_FLAG,
                matched_field="error_description",
                matched_rule=f"Matched risk keyword: '{keyword}' in description",
                reasoning=f"Payment flagged by risk engine ('{keyword}'). Requires human escalation only.",
                error_code=data.error_code,
                error_reason=data.error_reason
            )

    # ========================================================================
    # RULE 2: HARD_DECLINE (Permanent Failures & State Halts)
    # ========================================================================
    if data.event_type == "subscription.halted" or data.subscription_status == "halted":
        return ClassificationResult(
            bucket=DeclineBucket.HARD_DECLINE,
            matched_field="subscription_status",
            matched_rule="Subscription state transitioned to 'halted'",
            reasoning="Subscription entered 'halted' state after exhausting automated retries. Requires customer payment method update.",
            error_code=data.error_code,
            error_reason=data.error_reason
        )

    if reason_norm in HARD_DECLINE_REASONS:
        return ClassificationResult(
            bucket=DeclineBucket.HARD_DECLINE,
            matched_field="error_reason",
            matched_rule=f"Matched documented hard decline reason: '{reason_norm}'",
            reasoning=f"Permanent instrument/mandate failure ('{reason_norm}'). Automated retry will not succeed without customer updating payment details.",
            error_code=data.error_code,
            error_reason=data.error_reason
        )

    for keyword in ["expired card", "card is expired", "token not eligible", "mandate cancelled", "mandate revoked", "account closed", "card inactive"]:
        if keyword in desc_norm:
            return ClassificationResult(
                bucket=DeclineBucket.HARD_DECLINE,
                matched_field="error_description",
                matched_rule=f"Matched hard decline keyword: '{keyword}' in description",
                reasoning=f"Payment failure indicates invalid or expired credentials ('{keyword}'). Nudge customer to update card.",
                error_code=data.error_code,
                error_reason=data.error_reason
            )

    # ========================================================================
    # RULE 3: SOFT_DECLINE (Transient / Recoverable Failures)
    # ========================================================================
    if reason_norm in SOFT_DECLINE_REASONS or reason_norm == "insufficient_funds":
        return ClassificationResult(
            bucket=DeclineBucket.SOFT_DECLINE,
            matched_field="error_reason",
            matched_rule=f"Matched documented soft decline reason: '{reason_norm or 'insufficient_funds'}'",
            reasoning=f"Transient failure detected ('{reason_norm}'). High probability of recovery on scheduled automated retry.",
            error_code=data.error_code,
            error_reason=data.error_reason
        )

    if code_norm in {"GATEWAY_ERROR", "SERVER_ERROR"} or source_norm in {"gateway", "bank"}:
        return ClassificationResult(
            bucket=DeclineBucket.SOFT_DECLINE,
            matched_field="error_code/source",
            matched_rule=f"Gateway/Bank transient error (code: {code_norm}, source: {source_norm})",
            reasoning="Transient bank/gateway processing error. Eligible for automated retry with exponential backoff.",
            error_code=data.error_code,
            error_reason=data.error_reason
        )

    if data.event_type == "subscription.pending" or data.subscription_status == "pending":
        return ClassificationResult(
            bucket=DeclineBucket.SOFT_DECLINE,
            matched_field="subscription_status",
            matched_rule="Subscription state is 'pending'",
            reasoning="Subscription entered 'pending' state during automated retry window. Scheduled retry policy applies.",
            error_code=data.error_code,
            error_reason=data.error_reason
        )

    # Fallback default: Default to SOFT_DECLINE if transient failure with generic code, but log notice
    logger.info(f"Unmapped decline pattern (code={code_norm}, reason={reason_norm}). Defaulting to SOFT_DECLINE with low risk.")
    return ClassificationResult(
        bucket=DeclineBucket.SOFT_DECLINE,
        matched_field="fallback",
        matched_rule="Generic transient payment failure fallback",
        reasoning=f"Unclassified payment failure (code='{code_norm}', reason='{reason_norm}'). Assumed transient soft decline.",
        error_code=data.error_code,
        error_reason=data.error_reason
    )


def classify_webhook_payload(payload: Dict[str, Any]) -> Tuple[ExtractedFailureData, ClassificationResult]:
    """Convenience helper: extracts failure data and executes classification."""
    extracted = extract_failure_data(payload)
    result = classify_decline(extracted)
    return extracted, result
