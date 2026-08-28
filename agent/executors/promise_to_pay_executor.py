"""
Promise-to-Pay Executor & Tracking (Phase 3).

Guarantees:
1. Records customer promise-to-pay commitments with a promised date.
2. Checks in on or after the promised date.
3. Strictly enforces EXACTLY-ONCE check-in before payment status is re-evaluated.
"""
import datetime
import logging
from typing import Dict, Any, Optional

from db.repository import (
    record_promise_to_pay,
    get_active_promise_to_pay,
    check_in_promise_to_pay,
    get_all_promise_to_pay
)

logger = logging.getLogger(__name__)


def record_customer_promise(
    subscription_id: str,
    promised_date: str,  # YYYY-MM-DD
    customer_id: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Records a customer commitment to pay by a specified date."""
    logger.info(f"[PROMISE-TO-PAY] Logging promise for subscription '{subscription_id}' on date '{promised_date}'.")
    return record_promise_to_pay(
        subscription_id=subscription_id,
        promised_date=promised_date,
        customer_id=customer_id,
        notes=notes
    )


def evaluate_and_check_in_promise(
    subscription_id: str,
    current_date: Optional[str] = None  # YYYY-MM-DD
) -> Dict[str, Any]:
    """
    Evaluates promise-to-pay check-in:
    - If no pending promise exists -> returns no active promise.
    - If check_in_count >= 1 -> STRICTLY BLOCKS second automatic check-in.
    - If current_date < promised_date -> holds until promised date.
    - If current_date >= promised_date and check_in_count == 0 -> checks in exactly ONCE.
    """
    today_str = current_date or datetime.date.today().isoformat()
    promise = get_active_promise_to_pay(subscription_id)

    if not promise:
        # Check all promises to see if already checked in
        all_p = get_all_promise_to_pay(subscription_id)
        if all_p and all_p[0].get("check_in_count", 0) >= 1:
            logger.warning(
                f"[PROMISE-TO-PAY GUARDRAIL] Subscription '{subscription_id}' already had 1 check-in. "
                f"Second check-in strictly blocked."
            )
            return {
                "checked_in": False,
                "reason": "Already checked in once on promised date. Second automatic check-in forbidden until payment re-evaluation.",
                "check_in_count": all_p[0].get("check_in_count", 1)
            }
        return {
            "checked_in": False,
            "reason": f"No active promise-to-pay record found for subscription '{subscription_id}'."
        }

    # Check if already checked in
    if promise.get("check_in_count", 0) >= 1:
        logger.warning(
            f"[PROMISE-TO-PAY GUARDRAIL] Subscription '{subscription_id}' already checked in once "
            f"on {promise.get('last_checked_in_at')}. Second check-in blocked."
        )
        return {
            "checked_in": False,
            "reason": "Already checked in once on promised date. Second automatic check-in forbidden until payment re-evaluation.",
            "check_in_count": promise.get("check_in_count")
        }

    promised_date_str = str(promise.get("promised_date"))

    # Check if promised date reached
    if today_str < promised_date_str:
        logger.info(
            f"[PROMISE-TO-PAY] Promised date '{promised_date_str}' not reached yet (Today: '{today_str}'). Holding check-in."
        )
        return {
            "checked_in": False,
            "reason": f"Promised date '{promised_date_str}' is in future. Holding check-in.",
            "promised_date": promised_date_str,
            "today": today_str
        }

    # Promised date reached and 0 prior check-ins: Execute check-in exactly once
    updated_promise = check_in_promise_to_pay(promise["id"])
    logger.info(
        f"[PROMISE-TO-PAY] Executed exactly-once check-in for subscription '{subscription_id}' on promised date '{promised_date_str}'."
    )

    return {
        "checked_in": True,
        "subscription_id": subscription_id,
        "promised_date": promised_date_str,
        "check_in_count": 1,
        "status": "CHECKED_IN",
        "record": updated_promise
    }
