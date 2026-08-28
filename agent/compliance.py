"""
Compliance Guardrails Engine (Hard-coded safety boundaries).

Enforces:
1. RISK_FLAG isolation (Zero outreach and zero retries for fraud/security cases).
2. Customer opt-out enforcement.
3. Lifetime contact attempt caps across the entire subscription lifecycle.
4. Do-Not-Disturb (DND) contact hours (e.g., 9:00 AM - 8:00 PM IST).
"""
import datetime
import zoneinfo
import logging
from typing import Optional, Tuple
from db.config import settings
from db.repository import (
    is_subscription_opted_out,
    get_subscription_contact_count,
    get_subscription_recovery_state
)
from agent.models import ComplianceCheckResult

logger = logging.getLogger(__name__)


def get_current_ist_time() -> datetime.datetime:
    """Returns current time in the configured DND timezone (Asia/Kolkata)."""
    tz = zoneinfo.ZoneInfo(settings.DND_TIMEZONE)
    return datetime.datetime.now(tz)


def check_dnd_window(current_dt: Optional[datetime.datetime] = None) -> Tuple[bool, Optional[str]]:
    """
    Checks if the given time falls within the allowed contact window (e.g. 9:00 AM to 8:00 PM).
    
    Returns:
        Tuple of (is_allowed: bool, next_reschedule_iso: Optional[str])
    """
    tz = zoneinfo.ZoneInfo(settings.DND_TIMEZONE)
    dt = current_dt or datetime.datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)

    start_hour = settings.DND_END_HOUR   # e.g., 9 (9:00 AM)
    end_hour = settings.DND_START_HOUR   # e.g., 20 (8:00 PM)

    # Allowed window is [start_hour, end_hour) -> 09:00 to 19:59:59
    current_hour = dt.hour

    if start_hour <= current_hour < end_hour:
        return True, None

    # Blocked by DND -> Calculate next allowed window start
    if current_hour >= end_hour:
        # After 8 PM -> Reschedule to 9:00 AM next day
        next_allowed = (dt + datetime.timedelta(days=1)).replace(
            hour=start_hour, minute=0, second=0, microsecond=0
        )
    else:
        # Before 9 AM -> Reschedule to 9:00 AM today
        next_allowed = dt.replace(
            hour=start_hour, minute=0, second=0, microsecond=0
        )

    return False, next_allowed.isoformat()


def evaluate_contact_compliance(
    subscription_id: str,
    check_time: Optional[datetime.datetime] = None
) -> ComplianceCheckResult:
    """
    Evaluates all mandatory compliance guardrails before allowing any outbound customer nudge.
    
    Precedence:
    1. Risk / Fraud isolation check (Zero outreach permitted)
    2. Opt-out check (Permanent block)
    3. Lifetime contact cap (Subscription lifetime touch limit)
    4. DND hours (Time-of-day window check)
    """
    # 1. Check Risk Isolation
    state = get_subscription_recovery_state(subscription_id)
    if state and (state.get("status") == "ESCALATED_HUMAN_REVIEW" or state.get("last_bucket") == "RISK_FLAG"):
        logger.warning(
            f"[COMPLIANCE GUARDRAIL] Subscription '{subscription_id}' is flagged RISK_FLAG. Outreach strictly forbidden."
        )
        return ComplianceCheckResult(
            allowed=False,
            guardrail="RISK_FLAG",
            reason="Automated outreach forbidden on RISK_FLAG / human escalation subscription."
        )

    # 2. Check Opt-out
    if is_subscription_opted_out(subscription_id):
        logger.warning(
            f"[COMPLIANCE GUARDRAIL] Subscription '{subscription_id}' is opted-out. Outreach forbidden."
        )
        return ComplianceCheckResult(
            allowed=False,
            guardrail="OPT_OUT",
            reason="Customer has opted out of notifications. Automated outreach strictly blocked."
        )

    # 3. Check Lifetime Contact Cap
    contact_count = get_subscription_contact_count(subscription_id)
    if contact_count >= settings.MAX_LIFETIME_CONTACT_ATTEMPTS:
        logger.warning(
            f"[COMPLIANCE GUARDRAIL] Subscription '{subscription_id}' reached lifetime contact limit "
            f"({contact_count}/{settings.MAX_LIFETIME_CONTACT_ATTEMPTS}). Outreach forbidden."
        )
        return ComplianceCheckResult(
            allowed=False,
            guardrail="LIFETIME_CAP",
            reason=f"Global lifetime contact cap ({settings.MAX_LIFETIME_CONTACT_ATTEMPTS}) reached for subscription. Further outreach blocked."
        )

    # 4. Check DND Window
    allowed_dnd, next_window = check_dnd_window(check_time)
    if not allowed_dnd:
        logger.warning(
            f"[COMPLIANCE GUARDRAIL] Current time outside DND window (9am-8pm IST). "
            f"Outreach held. Rescheduled to: {next_window}"
        )
        return ComplianceCheckResult(
            allowed=False,
            guardrail="DND",
            reason=f"DND hours active (outside 09:00-20:00 {settings.DND_TIMEZONE}). Outreach held.",
            rescheduled_at=next_window
        )

    return ComplianceCheckResult(
        allowed=True,
        reason="Compliance checks passed: Within DND window, not opted out, lifetime cap within limits."
    )
