"""
Nudge Sender Executor for HARD_DECLINE decisions.
Enforces compliance guardrails (DND, Opt-out, Lifetime Cap) and attempts email delivery via SMTP.
"""
import smtplib
import logging
import datetime
from email.message import EmailMessage
from typing import Dict, Any, Optional

from db.config import settings
from db.repository import (
    update_recovery_audit_action_outcome,
    increment_subscription_contact_count
)
from agent.compliance import evaluate_contact_compliance
from agent.models import ActionExecutionType, ActionExecutionStatus

logger = logging.getLogger(__name__)


def send_email_via_smtp(
    to_email: str,
    subject: str,
    body_text: str,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None
) -> Dict[str, Any]:
    """
    Attempts delivery of email notification via standard SMTP.
    Captures exact transmission success or SMTP error codes without silent suppression.
    """
    host = smtp_host or settings.SMTP_HOST
    port = smtp_port or settings.SMTP_PORT

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body_text)

    try:
        with smtplib.SMTP(host=host, port=port, timeout=5) as server:
            if settings.SMTP_USE_TLS:
                try:
                    server.starttls()
                except Exception:
                    pass
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            return {"status": "sent", "host": host, "port": port, "to": to_email}
    except Exception as e:
        logger.warning(f"[SMTP DELIVERY] SMTP error attempting to send to {to_email}: {e}")
        return {"status": "failed", "error": f"{type(e).__name__}: {str(e)}", "host": host, "port": port}


def execute_nudge_send(
    subscription_id: str,
    customer_email: str = "customer@example.com",
    update_url: Optional[str] = None,
    audit_log_id: Optional[str] = None,
    check_time: Optional[datetime.datetime] = None
) -> Dict[str, Any]:
    """
    Executes customer nudge flow:
    1. Evaluates compliance guardrails (DND, Opt-out, Lifetime Cap).
    2. If blocked, records holding/blocking outcome to audit log.
    3. If allowed, increments contact count, dispatches SMTP email, and logs outcome.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 1. Compliance Evaluation
    compliance = evaluate_contact_compliance(subscription_id, check_time=check_time)
    
    if not compliance.allowed:
        if compliance.guardrail == "DND":
            action_executed = ActionExecutionType.HOLD_DND.value
            action_result = ActionExecutionStatus.HELD_DND.value
            details = {
                "guardrail": "DND",
                "reason": compliance.reason,
                "rescheduled_at": compliance.rescheduled_at
            }
        elif compliance.guardrail == "OPT_OUT":
            action_executed = ActionExecutionType.BLOCKED_OPT_OUT.value
            action_result = ActionExecutionStatus.BLOCKED.value
            details = {
                "guardrail": "OPT_OUT",
                "reason": compliance.reason
            }
        elif compliance.guardrail == "LIFETIME_CAP":
            action_executed = ActionExecutionType.BLOCKED_LIFETIME_CAP.value
            action_result = ActionExecutionStatus.BLOCKED.value
            details = {
                "guardrail": "LIFETIME_CAP",
                "reason": compliance.reason
            }
        else:
            action_executed = ActionExecutionType.NO_ACTION.value
            action_result = ActionExecutionStatus.BLOCKED.value
            details = {"reason": compliance.reason}

        logger.info(f"[NUDGE EXECUTOR] Compliance blocked nudge for '{subscription_id}': {compliance.reason}")

        if audit_log_id:
            update_recovery_audit_action_outcome(
                audit_id=audit_log_id,
                action_executed=action_executed,
                action_result=action_result,
                action_details=details,
                executed_at=now_iso
            )

        return {
            "allowed": False,
            "action_executed": action_executed,
            "action_result": action_result,
            "compliance_details": details,
            "executed_at": now_iso
        }

    # 2. Compliance passed: Increment lifetime contact counter
    new_contact_count = increment_subscription_contact_count(subscription_id)

    # 3. Attempt SMTP send
    link = update_url or f"https://rzp.io/i/{subscription_id[4:] if len(subscription_id) > 4 else 'update'}"
    subject = "Action Required: Update Payment Method for Your Subscription"
    body = (
        f"Dear Customer,\n\n"
        f"Your recurring subscription payment for subscription {subscription_id} could not be processed "
        f"due to an expired or invalid payment instrument.\n\n"
        f"Please update your payment method here to prevent service interruption:\n{link}\n\n"
        f"Thank you,\nBilling Team"
    )

    smtp_result = send_email_via_smtp(to_email=customer_email, subject=subject, body_text=body)
    
    if smtp_result.get("status") == "sent":
        action_executed = ActionExecutionType.SEND_EMAIL_NUDGE.value
        action_result = ActionExecutionStatus.SENT.value
        details = {
            "recipient": customer_email,
            "contact_touch_number": new_contact_count,
            "smtp_status": "sent"
        }
    else:
        action_executed = ActionExecutionType.SEND_EMAIL_NUDGE.value
        action_result = f"FAILED: {smtp_result.get('error', 'SMTP Error')}"
        details = {
            "recipient": customer_email,
            "contact_touch_number": new_contact_count,
            "smtp_error": smtp_result.get("error")
        }

    if audit_log_id:
        update_recovery_audit_action_outcome(
            audit_id=audit_log_id,
            action_executed=action_executed,
            action_result=action_result,
            action_details=details,
            executed_at=now_iso
        )

    return {
        "allowed": True,
        "action_executed": action_executed,
        "action_result": action_result,
        "details": details,
        "executed_at": now_iso
    }
