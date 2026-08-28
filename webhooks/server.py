"""
FastAPI Webhook Receiver, Decision Engine & Recovery Action Executor (Phases 1, 2 & 3).
Ingests raw events, verifies cryptographic signatures, persists raw payloads,
triggers deterministic decline classification & policy reasoning, and executes
recovery actions (Razorpay retry, SMTP nudge, risk escalation, and promise-to-pay tracking).
"""
import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, HTTPException, Header, status
from pydantic import BaseModel
import razorpay.errors

from db.config import settings
from db.repository import (
    save_raw_webhook,
    get_webhook_events,
    get_recovery_audit_logs,
    get_subscription_recovery_state,
    opt_out_subscription,
    is_subscription_opted_out
)
from webhooks.verifier import verify_razorpay_signature
from agent.decision_engine import process_webhook_decision
from agent.action_engine import execute_recovery_action
from agent.executors.promise_to_pay_executor import (
    record_customer_promise,
    evaluate_and_check_in_promise
)

# Configure structured logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("webhook-server")

app = FastAPI(
    title="Razorpay Subscription Payment Recovery Agent",
    version="3.0.0",
    description="Captures failure events, classifies decline reasons, enforces policy guardrails, and executes recovery actions."
)

# Supported failure events that trigger classification & policy reasoning
FAILURE_EVENTS = {
    "subscription.pending",
    "subscription.halted",
    "payment.failed"
}

# All supported subscription events
SUPPORTED_EVENTS = FAILURE_EVENTS | {
    "subscription.charged",
    "subscription.authenticated",
    "subscription.activated",
    "subscription.cancelled",
    "subscription.paused",
    "subscription.resumed"
}


# Request models for customer response simulation
class PromiseToPayRequest(BaseModel):
    promised_date: str  # YYYY-MM-DD
    customer_id: Optional[str] = None
    notes: Optional[str] = None


class CheckPromiseRequest(BaseModel):
    current_date: Optional[str] = None  # YYYY-MM-DD for testing


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Razorpay Recovery Agent (Webhook Ingestion + Decision Engine + Action Executor)",
        "environment": settings.ENVIRONMENT,
        "supported_events": list(SUPPORTED_EVENTS),
        "phase": "Phase 3 (Recovery Action Execution & Compliance Guardrails)"
    }


@app.post("/webhook", tags=["Webhooks"], status_code=status.HTTP_200_OK)
@app.post("/api/v1/webhooks/razorpay", tags=["Webhooks"], status_code=status.HTTP_200_OK)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str = Header(None, alias="X-Razorpay-Event-Id")
):
    """
    Receives, authenticates, logs raw payload, executes Phase 2 decline classification & policy reasoning,
    and executes Phase 3 recovery actions (retry / nudge / escalation).
    """
    # 1. Read raw body bytes
    raw_body = await request.body()

    if not raw_body:
        logger.warning("Rejected webhook: Empty request body.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty request body"
        )

    # 2. Verify cryptographic signature
    if not x_razorpay_signature:
        logger.warning("Rejected webhook: Missing X-Razorpay-Signature header.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header"
        )

    try:
        verify_razorpay_signature(
            body=raw_body,
            signature=x_razorpay_signature,
            secret=settings.RAZORPAY_WEBHOOK_SECRET
        )
    except razorpay.errors.SignatureVerificationError as e:
        logger.warning(f"Signature Verification Failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature"
        )
    except Exception as e:
        logger.error(f"Unexpected error in signature verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Verification error: {str(e)}"
        )

    # 3. Parse JSON payload
    try:
        payload_data: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body"
        )

    event_name = payload_data.get("event", "unknown")
    event_id = x_razorpay_event_id or payload_data.get("event_id") or payload_data.get("id")

    logger.info(f"Accepted webhook event: '{event_name}' (Event ID: {event_id})")

    # 4. Phase 1: Save raw payload into database (Raw capture NEVER stops)
    headers_to_save = {
        "x-razorpay-signature": x_razorpay_signature,
        "x-razorpay-event-id": x_razorpay_event_id,
        "content-type": request.headers.get("content-type"),
        "user-agent": request.headers.get("user-agent")
    }

    stored_record = save_raw_webhook(
        event_type=event_name,
        payload=payload_data,
        headers=headers_to_save,
        signature_valid=True,
        event_id=event_id
    )

    decision_info = None
    action_info = None

    # 5. Phase 2: If failure event, execute classification & policy decision logging
    if event_name in FAILURE_EVENTS:
        try:
            extracted, classification, decision, audit_row = process_webhook_decision(payload_data)
            decision_info = {
                "decline_bucket": decision.bucket.value,
                "decided_action": decision.action.value,
                "reasoning": decision.reasoning,
                "attempt_number": decision.attempt_number,
                "retry_delay_seconds": decision.retry_delay_seconds,
                "lifecycle_state": decision.lifecycle_state.value,
                "audit_log_id": audit_row.get("id") if audit_row else None
            }

            # 6. Phase 3: Execute the decided recovery action & update continuous audit trail
            if audit_row and audit_row.get("id"):
                action_res = execute_recovery_action(
                    decision=decision,
                    audit_log_id=audit_row.get("id"),
                    customer_email=extracted.customer_email
                )
                action_info = {
                    "action_executed": action_res.get("action_executed"),
                    "action_result": action_res.get("action_result")
                }
        except Exception as e:
            logger.error(f"Error during decision / action processing for event {event_name}: {e}", exc_info=True)

    # 7. Return acknowledgment
    response_body = {
        "status": "success",
        "message": "Webhook received, stored, and evaluated",
        "event": event_name,
        "raw_record_id": stored_record.get("id")
    }
    if decision_info:
        response_body["decision"] = decision_info
    if action_info:
        response_body["action_executed"] = action_info

    return response_body


@app.post("/api/v1/subscriptions/{subscription_id}/promise-to-pay", tags=["Promise-to-Pay"])
async def create_promise_to_pay(subscription_id: str, req: PromiseToPayRequest):
    """
    Simulates customer reply committing to pay by a specific date.
    """
    record = record_customer_promise(
        subscription_id=subscription_id,
        promised_date=req.promised_date,
        customer_id=req.customer_id,
        notes=req.notes
    )
    return {
        "status": "success",
        "message": f"Promise-to-pay recorded for {req.promised_date}",
        "promise": record
    }


@app.post("/api/v1/subscriptions/{subscription_id}/check-promise", tags=["Promise-to-Pay"])
async def check_promise(subscription_id: str, req: Optional[CheckPromiseRequest] = None):
    """
    Checks in on an active promise-to-pay (strictly exactly-once enforcement).
    """
    cur_date = req.current_date if req else None
    result = evaluate_and_check_in_promise(subscription_id=subscription_id, current_date=cur_date)
    return result


@app.post("/api/v1/subscriptions/{subscription_id}/opt-out", tags=["Compliance"])
async def opt_out(subscription_id: str):
    """
    Flags a customer / subscription as opted-out of all further notifications.
    """
    state = opt_out_subscription(subscription_id)
    return {
        "status": "success",
        "message": f"Subscription '{subscription_id}' successfully opted out of all notifications.",
        "is_opted_out": state.get("is_opted_out", True)
    }


@app.get("/webhooks/recent", tags=["Audit"])
async def get_recent_webhooks(limit: int = 20):
    """Retrieves recent raw webhook events."""
    events = get_webhook_events(limit=limit)
    return {
        "count": len(events),
        "events": events
    }


@app.get("/audit/decisions", tags=["Audit"])
async def get_recent_decision_logs(limit: int = 50, subscription_id: Optional[str] = None):
    """Retrieves continuous decision-to-outcome audit log rows."""
    logs = get_recovery_audit_logs(subscription_id=subscription_id, limit=limit)
    return {
        "count": len(logs),
        "decisions": logs
    }


@app.get("/audit/subscriptions/{subscription_id}/state", tags=["Audit"])
async def get_sub_state(subscription_id: str):
    """Retrieves current recovery state for a subscription."""
    state = get_subscription_recovery_state(subscription_id)
    if not state:
        raise HTTPException(status_code=404, detail="Subscription recovery state not found")
    return state
