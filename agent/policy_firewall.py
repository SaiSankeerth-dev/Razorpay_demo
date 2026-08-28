"""
Deterministic Policy Firewall & Financial Safety Boundary.

Architecture Invariant:
----------------------
AI Recommends. Deterministic Policy Authorizes.

The Policy Firewall sits directly between the AI Diagnostician and the Action Executors.
It enforces hard-coded stopping rules, retry budgets, risk isolation, and regulatory
compliance boundaries. No AI model output can bypass this firewall.
"""
import logging
from typing import Optional, Dict, Any

from agent.models import (
    AIDiagnosisResult,
    ClassificationResult,
    ExtractedFailureData,
    PolicyFirewallDecision,
    DecidedAction,
    DeclineBucket,
    SubscriptionLifecycleState,
    ComplianceCheckResult
)
from agent.compliance import evaluate_contact_compliance
from db.repository import (
    get_subscription_recovery_state,
    is_subscription_opted_out,
    get_subscription_contact_count
)

logger = logging.getLogger(__name__)

# Non-negotiable policy constants
MAX_RETRY_BUDGET = 3
MIN_BACKOFF_SCHEDULE = {
    1: 3600,    # 1 hour
    2: 21600,   # 6 hours
    3: 86400    # 24 hours
}


class PolicyFirewall:
    """
    Deterministic Policy Firewall.
    Validates, authorizes, or overrides AI recommendations before financial action execution.
    """

    @classmethod
    def evaluate(
        cls,
        ai_recommendation: AIDiagnosisResult,
        classification: ClassificationResult,
        failure_data: ExtractedFailureData,
        current_attempt_count: int = 0,
        is_already_terminal: bool = False,
        current_lifecycle_state: Optional[SubscriptionLifecycleState] = None
    ) -> PolicyFirewallDecision:
        sub_id = failure_data.subscription_id or "unknown_sub"
        rec_action = ai_recommendation.recommended_action

        # ====================================================================
        # GUARD 1: GLOBAL STOPPING RULE & TERMINAL STATE IDEMPOTENCY
        # ====================================================================
        if is_already_terminal or current_lifecycle_state in {
            SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS,
            SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW
        }:
            logger.warning(
                f"[FIREWALL OVERRIDE] Sub '{sub_id}' is already terminal ({current_lifecycle_state}). "
                f"Blocking AI recommendation '{rec_action.value}'."
            )
            return PolicyFirewallDecision(
                is_approved=False,
                authorized_action=DecidedAction.NO_ACTION_ALREADY_STOPPED,
                override_applied=True,
                override_reason=f"Global Stopping Rule: Subscription '{sub_id}' is in terminal state '{current_lifecycle_state}'. Replayed webhook acknowledged without re-triggering actions.",
                policy_rule_id="RULE_FIREWALL_TERMINAL_STOP",
                effective_delay_seconds=0,
                lifecycle_state=current_lifecycle_state or SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS,
                is_terminal=True
            )


        # ====================================================================
        # GUARD 2: RISK DECLINE ISOLATION (ZERO CONTACT, ZERO RETRY)
        # ====================================================================
        if classification.bucket == DeclineBucket.RISK_FLAG:
            if rec_action != DecidedAction.ESCALATE_TO_HUMAN:
                logger.warning(
                    f"[FIREWALL SECURITY OVERRIDE] Sub '{sub_id}' is RISK_FLAG. "
                    f"Overriding unsafe AI recommendation '{rec_action.value}' -> ESCALATE_TO_HUMAN."
                )
                return PolicyFirewallDecision(
                    is_approved=False,
                    authorized_action=DecidedAction.ESCALATE_TO_HUMAN,
                    override_applied=True,
                    override_reason="Security / Risk quarantine: AI recommended unsafe retry/nudge on suspected fraud/risk.",
                    policy_rule_id="RULE_FIREWALL_RISK_QUARANTINE",
                    effective_delay_seconds=0,
                    lifecycle_state=SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW,
                    is_terminal=True
                )
            else:
                return PolicyFirewallDecision(
                    is_approved=True,
                    authorized_action=DecidedAction.ESCALATE_TO_HUMAN,
                    override_applied=False,
                    override_reason=None,
                    policy_rule_id="RULE_FIREWALL_RISK_APPROVED",
                    effective_delay_seconds=0,
                    lifecycle_state=SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW,
                    is_terminal=True
                )

        # ====================================================================
        # GUARD 3: RETRY BUDGET CEILING (MAX 3 RETRIES)
        # ====================================================================
        if rec_action == DecidedAction.SCHEDULE_RETRY:
            next_attempt = current_attempt_count + 1
            if next_attempt > MAX_RETRY_BUDGET:
                logger.warning(
                    f"[FIREWALL OVERRIDE] Sub '{sub_id}' reached retry ceiling ({current_attempt_count}/{MAX_RETRY_BUDGET}). "
                    f"Overriding AI retry recommendation -> STOPPED_MAX_ATTEMPTS."
                )
                return PolicyFirewallDecision(
                    is_approved=False,
                    authorized_action=DecidedAction.NUDGE_PAYMENT_UPDATE,
                    override_applied=True,
                    override_reason=f"Automated retry limit reached ({current_attempt_count}/{MAX_RETRY_BUDGET} attempts exhausted). Stopping automated retries. Escalating to customer update nudge.",
                    policy_rule_id="RULE_FIREWALL_MAX_RETRY_BUDGET_EXHAUSTED",
                    effective_delay_seconds=0,
                    lifecycle_state=SubscriptionLifecycleState.STOPPED_MAX_ATTEMPTS,
                    is_terminal=True
                )


            # Prevent retrying permanent hard declines
            if classification.bucket == DeclineBucket.HARD_DECLINE:
                logger.warning(
                    f"[FIREWALL OVERRIDE] Sub '{sub_id}' is HARD_DECLINE. "
                    f"Overriding AI retry recommendation -> NUDGE_PAYMENT_UPDATE."
                )
                return PolicyFirewallDecision(
                    is_approved=False,
                    authorized_action=DecidedAction.NUDGE_PAYMENT_UPDATE,
                    override_applied=True,
                    override_reason="Permanent credential invalidation cannot be recovered via debit retry. Nudge required.",
                    policy_rule_id="RULE_FIREWALL_HARD_DECLINE_NUDGE_ONLY",
                    effective_delay_seconds=0,
                    lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE,
                    is_terminal=False
                )

            # Valid Soft Decline Retry: calculate minimum backoff delay
            ai_delay_sec = ai_recommendation.recommended_delay_hours * 3600
            min_delay_sec = MIN_BACKOFF_SCHEDULE.get(next_attempt, 3600)
            effective_delay = max(ai_delay_sec, min_delay_sec)

            return PolicyFirewallDecision(
                is_approved=True,
                authorized_action=DecidedAction.SCHEDULE_RETRY,
                override_applied=False,
                override_reason=None,
                policy_rule_id="RULE_FIREWALL_RETRY_APPROVED",
                effective_delay_seconds=effective_delay,
                lifecycle_state=SubscriptionLifecycleState.ACTIVE_RECOVERY,
                is_terminal=False
            )

        # ====================================================================
        # GUARD 4: CUSTOMER NUDGE AUTHORIZATION (HARD DECLINE / MANUAL RECOVERY)
        # ====================================================================
        if rec_action == DecidedAction.NUDGE_PAYMENT_UPDATE:
            return PolicyFirewallDecision(
                is_approved=True,
                authorized_action=DecidedAction.NUDGE_PAYMENT_UPDATE,
                override_applied=False,
                override_reason=None,
                policy_rule_id="RULE_FIREWALL_NUDGE_APPROVED",
                effective_delay_seconds=0,
                lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE,
                is_terminal=False
            )


        # Default fallback
        return PolicyFirewallDecision(
            is_approved=True,
            authorized_action=rec_action,
            override_applied=False,
            override_reason=None,
            policy_rule_id="RULE_FIREWALL_DEFAULT_PASSTHROUGH",
            effective_delay_seconds=0,
            lifecycle_state=current_lifecycle_state or SubscriptionLifecycleState.ACTIVE_RECOVERY,
            is_terminal=False
        )
