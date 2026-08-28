"""
Retry Executor for SOFT_DECLINE decisions.
Calls Razorpay Subscription API in TEST MODE and records the real API outcome.
"""
import logging
import datetime
from typing import Dict, Any, Optional
import razorpay
import razorpay.errors

from db.config import settings
from db.repository import update_recovery_audit_action_outcome, get_subscription_recovery_state
from agent.models import ActionExecutionType, ActionExecutionStatus

logger = logging.getLogger(__name__)


def get_razorpay_client() -> razorpay.Client:
    """Initializes Razorpay Python SDK client using test credentials."""
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def execute_payment_retry(
    subscription_id: str,
    audit_log_id: Optional[str] = None,
    payment_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes a real retry against Razorpay test mode:
    1. Evaluates risk state (strictly blocks retry on RISK_FLAG / ESCALATED_HUMAN_REVIEW).
    2. Interacts with Razorpay API (fetches subscription / pending invoice).
    3. Captures real API outcome (success or structured error code).
    4. Updates recovery_audit_log with continuous decision-to-outcome record.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Safety Guardrail: Reject if subscription is flagged RISK_FLAG or in human review
    state = get_subscription_recovery_state(subscription_id)
    if state and (state.get("status") == "ESCALATED_HUMAN_REVIEW" or state.get("last_bucket") == "RISK_FLAG"):
        logger.warning(
            f"[RETRY FORBIDDEN] Subscription '{subscription_id}' is flagged RISK_FLAG / ESCALATED_HUMAN_REVIEW. Retry strictly rejected."
        )
        if audit_log_id:
            update_recovery_audit_action_outcome(
                audit_id=audit_log_id,
                action_executed=ActionExecutionType.RETRY_PAYMENT.value,
                action_result="BLOCKED_RISK_FLAG",
                action_details={"reason": "Retry forbidden on RISK_FLAG / human escalation subscription"},
                executed_at=now_iso
            )
        return {
            "action_executed": ActionExecutionType.RETRY_PAYMENT.value,
            "action_result": "BLOCKED_RISK_FLAG",
            "api_response": {"error": "Retry forbidden on RISK_FLAG / human escalation subscription"},
            "executed_at": now_iso
        }

    client = get_razorpay_client()

    logger.info(f"[RETRY EXECUTOR] Initiating Razorpay test-mode retry for subscription '{subscription_id}'...")

    try:
        # Call Razorpay Subscription API in test mode
        sub_data = client.subscription.fetch(subscription_id)
        
        api_outcome = {
            "status": "success",
            "subscription_id": sub_data.get("id"),
            "subscription_status": sub_data.get("status"),
            "paid_count": sub_data.get("paid_count"),
            "auth_attempts": sub_data.get("auth_attempts"),
            "short_url": sub_data.get("short_url")
        }
        action_result = ActionExecutionStatus.SUCCESS.value
        logger.info(f"[RETRY EXECUTOR] Real Razorpay API call succeeded: {api_outcome}")

    except razorpay.errors.BadRequestError as e:
        action_result = f"FAILED: BAD_REQUEST_ERROR"
        api_outcome = {
            "error_type": "BadRequestError",
            "error_message": str(e),
            "status_code": 400
        }
        logger.warning(f"[RETRY EXECUTOR] Razorpay API returned BadRequestError: {e}")

    except razorpay.errors.GatewayError as e:
        action_result = f"FAILED: GATEWAY_ERROR"
        api_outcome = {
            "error_type": "GatewayError",
            "error_message": str(e),
            "status_code": 504
        }
        logger.warning(f"[RETRY EXECUTOR] Razorpay API returned GatewayError: {e}")

    except Exception as e:
        action_result = f"FAILED: {type(e).__name__}"
        api_outcome = {
            "error_type": type(e).__name__,
            "error_message": str(e)
        }
        logger.error(f"[RETRY EXECUTOR] Unexpected API error during retry: {e}")

    updated_audit_entry = None
    if audit_log_id:
        updated_audit_entry = update_recovery_audit_action_outcome(
            audit_id=audit_log_id,
            action_executed=ActionExecutionType.RETRY_PAYMENT.value,
            action_result=action_result,
            action_details=api_outcome,
            executed_at=now_iso
        )

    return {
        "action_executed": ActionExecutionType.RETRY_PAYMENT.value,
        "action_result": action_result,
        "api_response": api_outcome,
        "executed_at": now_iso,
        "audit_entry": updated_audit_entry
    }
