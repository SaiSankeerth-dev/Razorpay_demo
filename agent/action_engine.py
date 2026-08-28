"""
Recovery Action Engine (Phase 3 Orchestrator).
Dispatches and executes the recovery actions decided by Phase 2 policy evaluation,
updating the continuous decision-to-outcome audit trail.
"""
import logging
import datetime
from typing import Dict, Any, Optional

from agent.models import (
    PolicyDecision,
    DecidedAction,
    AuditLogEntry
)
from agent.executors.retry_executor import execute_payment_retry
from agent.executors.nudge_executor import execute_nudge_send
from agent.executors.escalation_executor import execute_risk_escalation
from db.repository import get_recovery_audit_logs

logger = logging.getLogger(__name__)


def execute_recovery_action(
    decision: PolicyDecision,
    audit_log_id: Optional[str] = None,
    customer_email: Optional[str] = None,
    check_time: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Executes the action corresponding to a PolicyDecision:
    - SCHEDULE_RETRY -> calls Razorpay test-mode retry mechanism
    - NUDGE_PAYMENT_UPDATE -> checks compliance & sends SMTP email nudge
    - ESCALATE_TO_HUMAN -> flags for manual compliance review (0 outreach, 0 retry)
    - NO_ACTION_ALREADY_STOPPED -> ignores (idempotency guard)
    """
    sub_id = decision.subscription_id
    email = customer_email or "customer.recovery@example.com"

    if decision.action == DecidedAction.SCHEDULE_RETRY:
        return execute_payment_retry(
            subscription_id=sub_id,
            audit_log_id=audit_log_id
        )

    elif decision.action == DecidedAction.NUDGE_PAYMENT_UPDATE:
        return execute_nudge_send(
            subscription_id=sub_id,
            customer_email=email,
            audit_log_id=audit_log_id,
            check_time=check_time
        )

    elif decision.action == DecidedAction.ESCALATE_TO_HUMAN:
        return execute_risk_escalation(
            subscription_id=sub_id,
            audit_log_id=audit_log_id,
            reasoning=decision.reasoning
        )

    elif decision.action == DecidedAction.NO_ACTION_ALREADY_STOPPED:
        logger.info(f"[ACTION ENGINE] No action executed for stopped subscription '{sub_id}'.")
        return {
            "action_executed": "NO_ACTION",
            "action_result": "BLOCKED_TERMINAL_STATE",
            "subscription_id": sub_id
        }

    return {
        "action_executed": "UNKNOWN",
        "action_result": "FAILED",
        "subscription_id": sub_id
    }
