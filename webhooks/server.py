"""
FastAPI Webhook Receiver for Razorpay Subscription Events.
Ingests raw events, verifies cryptographic signatures, and stores them in Supabase.
"""
import json
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, Request, HTTPException, Header, status
from fastapi.responses import JSONResponse
import razorpay.errors

from db.config import settings
from db.repository import save_raw_webhook, get_webhook_events
from webhooks.verifier import verify_razorpay_signature

# Configure structured logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("webhook-server")

app = FastAPI(
    title="Razorpay Subscription Payment Recovery Webhook Receiver",
    version="1.0.0",
    description="Captures and logs Razorpay subscription failure and state change events."
)

# Supported events for recovery agent
SUPPORTED_EVENTS = {
    "subscription.pending",
    "subscription.halted",
    "payment.failed",
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
        "service": "Razorpay Recovery Webhook Ingestor",
        "environment": settings.ENVIRONMENT,
        "supported_events": list(SUPPORTED_EVENTS)
    }


@app.post("/webhook", tags=["Webhooks"], status_code=status.HTTP_200_OK)
@app.post("/api/v1/webhooks/razorpay", tags=["Webhooks"], status_code=status.HTTP_200_OK)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str = Header(None, alias="X-Razorpay-Event-Id")
):
    """
    Receives, authenticates, and stores Razorpay webhook events.

    1. Reads the exact raw payload bytes.
    2. Cryptographically verifies HMAC-SHA256 signature against RAZORPAY_WEBHOOK_SECRET.
    3. Rejects invalid / tampered requests immediately with HTTP 400.
    4. Saves raw, unmodified payload to Supabase database.
    5. Returns 200 OK to acknowledge receipt.
    """
    # 1. Read raw body bytes
    raw_body = await request.body()

    if not raw_body:
        logger.warning("Rejected webhook: Empty request body.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty request body"
        )

    # 2. Verify signature
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

    # 4. Save raw payload into database
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

    # 5. Return success acknowledgment
    return {
        "status": "success",
        "message": "Webhook received and logged",
        "event": event_name,
        "record_id": stored_record.get("id")
    }


@app.get("/webhooks/recent", tags=["Audit"])
async def get_recent_webhooks(limit: int = 20):
    """
    Retrieves recent captured raw webhook events from the database.
    """
    events = get_webhook_events(limit=limit)
    return {
        "count": len(events),
        "events": events
    }
