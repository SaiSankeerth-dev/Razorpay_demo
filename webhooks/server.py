"""
FastAPI Webhook Receiver & Decision Engine for Razorpay Subscription Recovery.
Ingests raw events, verifies cryptographic signatures, persists raw payloads,
and triggers deterministic decline classification & policy audit logging.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, HTTPException, Header, status
import razorpay.errors

from db.config import settings
from db.repository import (
    save_raw_webhook,
    get_webhook_events,
    get_recovery_audit_logs,
    get_subscription_recovery_state
)
from webhooks.verifier import verify_razorpay_signature
from agent.decision_engine import process_webhook_decision

# Configure structured logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("webhook-server")

app = FastAPI(
    title="Razorpay Subscription Payment Recovery Webhook & Decision Engine",
    version="2.0.0",
    description="Captures Razorpay subscription failure events, classifies decline reasons, and executes policy audit logging."
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


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Razorpay Recovery Webhook & Decision Engine",
        "environment": settings.ENVIRONMENT,
        "supported_events": list(SUPPORTED_EVENTS),
        "phase": "Phase 2 (Classification & Policy Reasoning)"
    }


@app.post("/webhook", tags=["Webhooks"], status_code=status.HTTP_200_OK)
@app.post("/api/v1/webhooks/razorpay", tags=["Webhooks"], status_code=status.HTTP_200_OK)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str = Header(None, alias="X-Razorpay-Event-Id")
):
    """
    Receives, authenticates, logs raw payload, and executes Phase 2 decline classification & policy reasoning.
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

    # 4. Phase 1: Save raw payload into database
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

    # 5. Phase 2: If failure event, execute classification & policy decision logging
    if event_name in FAILURE_EVENTS:
        try:
            _, classification, decision, audit_row = process_webhook_decision(payload_data)
            decision_info = {
                "decline_bucket": decision.bucket.value,
                "decided_action": decision.action.value,
                "reasoning": decision.reasoning,
                "attempt_number": decision.attempt_number,
                "retry_delay_seconds": decision.retry_delay_seconds,
                "lifecycle_state": decision.lifecycle_state.value,
                "audit_log_id": audit_row.get("id")
            }
        except Exception as e:
            logger.error(f"Error during decision processing for event {event_name}: {e}", exc_info=True)

    # 6. Return success acknowledgment
    response_body = {
        "status": "success",
        "message": "Webhook received, stored, and evaluated",
        "event": event_name,
        "raw_record_id": stored_record.get("id")
    }
    if decision_info:
        response_body["decision"] = decision_info

    return response_body


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
    """Retrieves immutable decision audit log rows."""
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
