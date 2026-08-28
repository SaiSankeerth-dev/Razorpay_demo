"""
Deterministic Policy Engine for Subscription Payment Recovery.

CRITICAL ARCHITECTURAL DECISION:
Why Hard-Coded Deterministic Rules vs LLM Judgment?
--------------------------------------------------
The policy engine enforces financial safety boundaries, compliance invariants, and
hard stopping rules (e.g., RBI recurring mandate retry guidelines and payment scheme rules).
Leaving retry counts, backoff timing, or risk escalation to non-deterministic model judgment
introduces unacceptable risks of runaway retries, regulatory violations, and unauthorized debits.
Therefore, policy execution is strictly hard-coded, deterministic, and immutable.
"""
import logging
from typing import Optional, Dict, Any
from agent.models import (
    DeclineBucket,
    DecidedAction,
    SubscriptionLifecycleState,
    ClassificationResult,
    PolicyDecision,
    ExtractedFailureData
)

logger = logging.getLogger(__name__)

# ============================================================================
# POLICY CONFIGURATION CONSTANTS
# ============================================================================

MAX_RETRY_ATTEMPTS = 3

# Progressive backoff schedule (seconds): 1hr -> 6hr -> 24hr
RETRY_BACKOFF_SCHEDULE = {
    1: 3600,    # 1 hour
    2: 21600,   # 6 hours
    3: 86400    # 24 hours
}


class PolicyEngine:
    """
    Evaluates classification results against strict deterministic recovery policies.
    Enforces attempt limits, backoff schedules, and idempotency stopping rules.
    """

    @classmethod
    def evaluate(
        cls,
        classification: ClassificationResult,
        extracted_data: ExtractedFailureData,
        current_attempt_count: int = 0,
        is_already_terminal: bool = False,
        current_lifecycle_state: Optional[SubscriptionLifecycleState] = None
    ) -> PolicyDecision:
        """
        Evaluates the next action for a subscription failure event.

        Args:
            classification: Output from decline classifier
            extracted_data: Raw failure parameters
            current_attempt_count: Previous retry attempts already executed for this subscription
            is_already_terminal: Whether the subscription is already in a stopped/terminal state
            current_lifecycle_state: Current state in subscription recovery tracker

        Returns:
            PolicyDecision containing exact decided action, reasoning, and lifecycle state.
        """
        sub_id = extracted_data.subscription_id or "unknown_subscription"

        # ====================================================================
        # INVARIANT 1: GLOBAL STOPPING RULE & REPLAY IDEMPOTENCY
        # If the subscription is already in a terminal state (STOPPED or ESCALATED),
        # ALL automated actions are permanently blocked. Replays cannot reopen it.
        # ====================================================================
        if is_already_terminal or current_lifecycle_state in {
            SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS,
            SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
        }:
            logger.warning(
                f"[STOPPING RULE] Subscription '{sub_id}' is already in terminal state "
                f"'{current_lifecycle_state}'. Blocking all automated actions for replayed/subsequent webhook."
            )
            return PolicyDecision(
                action=DecidedAction.NO_ACTION_ALREADY_STOPPED,
                bucket=classification.bucket,
                subscription_id=sub_id,
                attempt_number=current_attempt_count,
                retry_delay_seconds=None,
                lifecycle_state=current_lifecycle_state or SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS,
                is_terminal=True,
                reasoning=(
                    f"Global Stopping Rule: Subscription '{sub_id}' is in terminal state "
                    f"'{current_lifecycle_state}'. Replayed webhook acknowledged without re-triggering actions."
                ),
                policy_rule_id="RULE_GLOBAL_STOP_IDEMPOTENT"
            )

        # ====================================================================
        # POLICY RULE 1: RISK_FLAG -> IMMEDIATE HUMAN ESCALATION
        # Never auto-retry, never send automated customer nudges.
        # ====================================================================
        if classification.bucket == DeclineBucket.RISK_FLAG:
            return PolicyDecision(
                action=DecidedAction.ESCALATE_TO_HUMAN,
                bucket=DeclineBucket.RISK_FLAG,
                subscription_id=sub_id,
                attempt_number=current_attempt_count,
                retry_delay_seconds=None,
                lifecycle_state=SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW,
                is_terminal=True,  # Terminal: requires manual human reopening
                reasoning=(
                    f"Security/Risk decline detected ({classification.matched_rule}). "
                    f"Halted all automated workflows. Flagged for manual compliance and fraud review."
                ),
                policy_rule_id="RULE_RISK_ESCALATE_HUMAN"
            )

        # ====================================================================
        # POLICY RULE 2: HARD_DECLINE -> PAYMENT METHOD UPDATE NUDGE
        # Never auto-retry (do not hit card networks with invalid/expired tokens).
        # ====================================================================
        if classification.bucket == DeclineBucket.HARD_DECLINE:
            return PolicyDecision(
                action=DecidedAction.NUDGE_PAYMENT_UPDATE,
                bucket=DeclineBucket.HARD_DECLINE,
                subscription_id=sub_id,
                attempt_number=current_attempt_count,
                retry_delay_seconds=None,
                lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE,
                is_terminal=False,  # Can recover once customer updates instrument
                reasoning=(
                    f"Permanent credential or mandate failure ({classification.matched_rule}). "
                    f"Automated retry blocked. Queued payment method update link for customer."
                ),
                policy_rule_id="RULE_HARD_DECLINE_NUDGE_UPDATE"
            )

        # ====================================================================
        # POLICY RULE 3: SOFT_DECLINE -> SCHEDULED RETRY (MAX 3 ATTEMPTS)
        # Transient failure. Check if within retry budget.
        # ====================================================================
        next_attempt_number = current_attempt_count + 1

        # Check if retry limit exceeded (Attempt #4 blocked)
        if next_attempt_number > MAX_RETRY_ATTEMPTS:
            logger.info(
                f"[MAX RETRIES EXCEEDED] Subscription '{sub_id}' exceeded max attempts "
                f"({MAX_RETRY_ATTEMPTS}). Transitioning to STOPPED_MAX_ATTEMPTS."
            )
            return PolicyDecision(
                action=DecidedAction.NUDGE_PAYMENT_UPDATE,
                bucket=DeclineBucket.SOFT_DECLINE,
                subscription_id=sub_id,
                attempt_number=next_attempt_number,
                retry_delay_seconds=None,
                lifecycle_state=SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS,
                is_terminal=True,  # Terminal: retry budget exhausted
                reasoning=(
                    f"Automated retry limit reached ({current_attempt_count}/{MAX_RETRY_ATTEMPTS} attempts exhausted). "
                    f"Stopping automated retries. Escalating to customer update nudge."
                ),
                policy_rule_id="RULE_SOFT_DECLINE_MAX_ATTEMPTS_REACHED"
            )

        # Within retry budget: calculate backoff delay
        delay_seconds = RETRY_BACKOFF_SCHEDULE.get(next_attempt_number, 86400)
        delay_hours = delay_seconds // 3600

        return PolicyDecision(
            action=DecidedAction.SCHEDULE_RETRY,
            bucket=DeclineBucket.SOFT_DECLINE,
            subscription_id=sub_id,
            attempt_number=next_attempt_number,
            retry_delay_seconds=delay_seconds,
            lifecycle_state=SubscriptionLifecycleState.ACTIVE_RECOVERY,
            is_terminal=False,
            reasoning=(
                f"Soft decline detected ({classification.matched_rule}). "
                f"Scheduled retry attempt #{next_attempt_number}/{MAX_RETRY_ATTEMPTS} with {delay_hours}h backoff delay."
            ),
            policy_rule_id=f"RULE_SOFT_DECLINE_RETRY_ATTEMPT_{next_attempt_number}"
        )
