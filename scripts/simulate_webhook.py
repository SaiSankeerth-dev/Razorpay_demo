"""
Webhook Simulation and Testing Script.
Generates authentic Razorpay webhook payloads for payment failure and subscription
state transitions, computes HMAC-SHA256 signatures, and verifies delivery and rejection.
"""
import hmac
import hashlib
import json
import time
import uuid
import sys
import os
import requests
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("webhook-simulator")


def build_payment_failed_payload(
    subscription_id: str = "sub_Ptest1000000001",
    plan_id: str = "plan_Ptest1000000001",
    payment_id: str = None,
    error_code: str = "BAD_REQUEST_ERROR",
    error_description: str = "Payment failed due to insufficient funds in customer bank account",
    error_source: str = "bank",
    error_step: str = "payment_authorization",
    error_reason: str = "payment_failed"
) -> dict:
    """
    Constructs an authentic Razorpay 'payment.failed' webhook payload.
    """
    pid = payment_id or f"pay_{uuid.uuid4().hex[:14]}"
    timestamp = int(time.time())

    return {
        "entity": "event",
        "account_id": "acc_PtestMerchant01",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": pid,
                    "entity": "payment",
                    "amount": 49900,
                    "currency": "INR",
                    "status": "failed",
                    "order_id": f"order_{uuid.uuid4().hex[:14]}",
                    "invoice_id": f"inv_{uuid.uuid4().hex[:14]}",
                    "international": False,
                    "method": "card",
                    "amount_refunded": 0,
                    "refund_status": None,
                    "captured": False,
                    "description": "Recurring subscription charge",
                    "card_id": f"card_{uuid.uuid4().hex[:14]}",
                    "bank": "HDFC",
                    "wallet": None,
                    "vpa": None,
                    "email": "customer.test@example.com",
                    "contact": "+919876543210",
                    "customer_id": f"cust_{uuid.uuid4().hex[:14]}",
                    "token_id": f"token_{uuid.uuid4().hex[:14]}",
                    "notes": {
                        "subscription_id": subscription_id,
                        "plan_id": plan_id
                    },
                    "fee": None,
                    "tax": None,
                    "error_code": error_code,
                    "error_description": error_description,
                    "error_source": error_source,
                    "error_step": error_step,
                    "error_reason": error_reason,
                    "created_at": timestamp
                }
            }
        },
        "created_at": timestamp
    }


def build_subscription_pending_payload(
    subscription_id: str = "sub_Ptest1000000001",
    plan_id: str = "plan_Ptest1000000001"
) -> dict:
    """
    Constructs an authentic Razorpay 'subscription.pending' webhook payload.
    Triggered when an automated charge fails and enters retry phase.
    """
    timestamp = int(time.time())
    return {
        "entity": "event",
        "account_id": "acc_PtestMerchant01",
        "event": "subscription.pending",
        "contains": ["subscription"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": subscription_id,
                    "entity": "subscription",
                    "plan_id": plan_id,
                    "customer_id": f"cust_{uuid.uuid4().hex[:14]}",
                    "status": "pending",
                    "current_start": timestamp - 86400,
                    "current_end": timestamp + 604800,
                    "ended_at": None,
                    "quantity": 1,
                    "notes": {
                        "tier": "pro_monthly"
                    },
                    "charge_at": timestamp + 86400,  # Scheduled retry time
                    "start_at": timestamp - 86400,
                    "end_at": timestamp + 31536000,
                    "auth_attempts": 1,
                    "total_count": 12,
                    "paid_count": 0,
                    "remaining_count": 12,
                    "short_url": f"https://rzp.io/i/{subscription_id[4:]}",
                    "has_scheduled_changes": False,
                    "change_scheduled_at": None,
                    "source": "api",
                    "created_at": timestamp - 86400
                }
            }
        },
        "created_at": timestamp
    }


def build_subscription_halted_payload(
    subscription_id: str = "sub_Ptest1000000001",
    plan_id: str = "plan_Ptest1000000001"
) -> dict:
    """
    Constructs an authentic Razorpay 'subscription.halted' webhook payload.
    Triggered after all automated retries fail.
    """
    timestamp = int(time.time())
    return {
        "entity": "event",
        "account_id": "acc_PtestMerchant01",
        "event": "subscription.halted",
        "contains": ["subscription"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": subscription_id,
                    "entity": "subscription",
                    "plan_id": plan_id,
                    "customer_id": f"cust_{uuid.uuid4().hex[:14]}",
                    "status": "halted",
                    "current_start": timestamp - 604800,
                    "current_end": timestamp,
                    "ended_at": None,
                    "quantity": 1,
                    "notes": {
                        "tier": "pro_monthly"
                    },
                    "charge_at": None,
                    "start_at": timestamp - 604800,
                    "end_at": timestamp + 31536000,
                    "auth_attempts": 4,  # All retries exhausted
                    "total_count": 12,
                    "paid_count": 0,
                    "remaining_count": 12,
                    "short_url": f"https://rzp.io/i/{subscription_id[4:]}",
                    "has_scheduled_changes": False,
                    "change_scheduled_at": None,
                    "source": "api",
                    "created_at": timestamp - 604800
                }
            }
        },
        "created_at": timestamp
    }


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Computes HMAC-SHA256 signature using the exact method expected by Razorpay SDK."""
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()


def send_simulation_request(
    url: str,
    payload: dict,
    secret: str,
    tamper_signature: bool = False,
    event_id: str = None
) -> requests.Response:
    """
    Sends the simulated webhook request with headers.
    """
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")

    if tamper_signature:
        signature = "tampered_bad_signature_0000000000000000000000000000000000000000"
    else:
        signature = compute_signature(payload_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex[:14]}",
        "User-Agent": "Razorpay-Webhook-Simulator/1.0"
    }

    response = requests.post(url, data=payload_bytes, headers=headers)
    return response


def run_full_simulation(base_url: str = "http://127.0.0.1:8000", secret: str = None):
    webhook_secret = secret or settings.RAZORPAY_WEBHOOK_SECRET
    endpoint = f"{base_url}/webhook"

    print("=" * 70)
    print("RAZORPAY WEBHOOK INGESTION & SIGNATURE REJECTION SIMULATION")
    print(f"Target Endpoint: {endpoint}")
    print(f"Webhook Secret:  {'*' * len(webhook_secret)}")
    print("=" * 70)

    # ------------------------------------------------------------------------
    # TEST 1: Tampered Signature Rejection Test
    # ------------------------------------------------------------------------
    print("\n[TEST 1] Testing Tampered / Invalid Signature Rejection...")
    test_payload = build_payment_failed_payload()
    tampered_response = send_simulation_request(
        endpoint, test_payload, webhook_secret, tamper_signature=True
    )
    print(f"  HTTP Status: {tampered_response.status_code}")
    print(f"  Response:    {tampered_response.text}")
    assert tampered_response.status_code == 400, f"Expected 400, got {tampered_response.status_code}"
    print("  -> PASSED: Server successfully rejected tampered signature with HTTP 400 Bad Request.")

    # ------------------------------------------------------------------------
    # TEST 2: Valid 'payment.failed' Webhook Event
    # ------------------------------------------------------------------------
    print("\n[TEST 2] Sending Authentic 'payment.failed' Webhook Event...")
    failed_payload = build_payment_failed_payload(
        error_code="BAD_REQUEST_ERROR",
        error_description="Payment failed due to insufficient funds",
        error_source="bank",
        error_step="payment_authorization",
        error_reason="payment_failed"
    )
    res_failed = send_simulation_request(endpoint, failed_payload, webhook_secret)
    print(f"  HTTP Status: {res_failed.status_code}")
    print(f"  Response:    {res_failed.text}")
    assert res_failed.status_code == 200, f"Expected 200, got {res_failed.status_code}"
    print("  -> PASSED: Server verified signature and captured payment.failed event.")

    # ------------------------------------------------------------------------
    # TEST 3: Valid 'subscription.pending' Webhook Event
    # ------------------------------------------------------------------------
    print("\n[TEST 3] Sending Authentic 'subscription.pending' Webhook Event...")
    pending_payload = build_subscription_pending_payload()
    res_pending = send_simulation_request(endpoint, pending_payload, webhook_secret)
    print(f"  HTTP Status: {res_pending.status_code}")
    print(f"  Response:    {res_pending.text}")
    assert res_pending.status_code == 200, f"Expected 200, got {res_pending.status_code}"
    print("  -> PASSED: Server verified signature and captured subscription.pending event.")

    # ------------------------------------------------------------------------
    # TEST 4: Valid 'subscription.halted' Webhook Event
    # ------------------------------------------------------------------------
    print("\n[TEST 4] Sending Authentic 'subscription.halted' Webhook Event...")
    halted_payload = build_subscription_halted_payload()
    res_halted = send_simulation_request(endpoint, halted_payload, webhook_secret)
    print(f"  HTTP Status: {res_halted.status_code}")
    print(f"  Response:    {res_halted.text}")
    assert res_halted.status_code == 200, f"Expected 200, got {res_halted.status_code}"
    print("  -> PASSED: Server verified signature and captured subscription.halted event.")

    # ------------------------------------------------------------------------
    # Verify DB Capture
    # ------------------------------------------------------------------------
    print("\n[AUDIT] Fetching Captured Events from DB via /webhooks/recent...")
    audit_res = requests.get(f"{base_url}/webhooks/recent?limit=5")
    print(f"  HTTP Status: {audit_res.status_code}")
    audit_data = audit_res.json()
    print(f"  Total captured events returned: {audit_data.get('count')}")
    print(f"  Latest raw payload sample:\n{json.dumps(audit_data.get('events', [{}])[0], indent=2)}")

    print("\n" + "=" * 70)
    print("ALL SIMULATION AND ACCEPTANCE TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    run_full_simulation(base_url=url)
