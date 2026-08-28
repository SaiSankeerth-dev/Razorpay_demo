"""
Webhook Simulation & Decision Audit Testing Script (Phase 1 + Phase 2).
Generates authentic Razorpay webhook payloads across all 3 decline buckets,
verifies signature validation/rejection, executes policy evaluations,
and queries the live decision audit trail.
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
    error_source: str = "customer",
    error_step: str = "payment_authorization",
    error_reason: str = "insufficient_funds"
) -> dict:
    """Constructs an authentic Razorpay 'payment.failed' webhook payload."""
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
    """Constructs an authentic Razorpay 'subscription.pending' webhook payload."""
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
                    "charge_at": timestamp + 86400,
                    "start_at": timestamp - 86400,
                    "end_at": timestamp + 31536000,
                    "auth_attempts": 1,
                    "total_count": 12,
                    "paid_count": 0,
                    "remaining_count": 12,
                    "short_url": f"https://rzp.io/i/{subscription_id[4:] if len(subscription_id) > 4 else 'xyz'}",
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
    """Constructs an authentic Razorpay 'subscription.halted' webhook payload."""
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
                    "auth_attempts": 4,
                    "total_count": 12,
                    "paid_count": 0,
                    "remaining_count": 12,
                    "short_url": f"https://rzp.io/i/{subscription_id[4:] if len(subscription_id) > 4 else 'xyz'}",
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
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")

    if tamper_signature:
        signature = "tampered_bad_signature_0000000000000000000000000000000000000000"
    else:
        signature = compute_signature(payload_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex[:14]}",
        "User-Agent": "Razorpay-Webhook-Simulator/2.0"
    }

    response = requests.post(url, data=payload_bytes, headers=headers)
    return response


def run_full_simulation(base_url: str = "http://127.0.0.1:8000", secret: str = None):
    webhook_secret = secret or settings.RAZORPAY_WEBHOOK_SECRET
    endpoint = f"{base_url}/webhook"

    print("=" * 75)
    print("PHASE 2: DECLINE CLASSIFICATION, POLICY ENGINE & AUDIT LOG SIMULATION")
    print(f"Target Endpoint: {endpoint}")
    print("=" * 75)

    # ------------------------------------------------------------------------
    # TEST 1: Tampered Signature Rejection
    # ------------------------------------------------------------------------
    print("\n[TEST 1] Testing Tampered Signature Rejection...")
    test_payload = build_payment_failed_payload()
    tampered_response = send_simulation_request(endpoint, test_payload, webhook_secret, tamper_signature=True)
    print(f"  HTTP Status: {tampered_response.status_code}")
    print(f"  Response:    {tampered_response.text}")
    assert tampered_response.status_code == 400
    print("  -> PASSED: Server rejected tampered signature (400 Bad Request).")

    # ------------------------------------------------------------------------
    # TEST 2: SOFT_DECLINE (insufficient_funds) -> SCHEDULE_RETRY
    # ------------------------------------------------------------------------
    print("\n[TEST 2] Category 1: SOFT_DECLINE (insufficient_funds)...")
    sub_soft_id = f"sub_demo_soft_{uuid.uuid4().hex[:6]}"
    soft_payload = build_payment_failed_payload(
        subscription_id=sub_soft_id,
        error_code="BAD_REQUEST_ERROR",
        error_description="Payment failed due to insufficient funds in customer bank account",
        error_source="customer",
        error_step="payment_authorization",
        error_reason="insufficient_funds"
    )
    res_soft = send_simulation_request(endpoint, soft_payload, webhook_secret)
    print(f"  HTTP Status: {res_soft.status_code}")
    res_soft_json = res_soft.json()
    print(f"  Decision:    {json.dumps(res_soft_json.get('decision'), indent=2)}")
    assert res_soft_json.get("decision", {}).get("decline_bucket") == "SOFT_DECLINE"
    assert res_soft_json.get("decision", {}).get("decided_action") == "SCHEDULE_RETRY"
    print("  -> PASSED: Correctly classified as SOFT_DECLINE -> SCHEDULE_RETRY.")

    # ------------------------------------------------------------------------
    # TEST 3: HARD_DECLINE (expired_card) -> NUDGE_PAYMENT_UPDATE
    # ------------------------------------------------------------------------
    print("\n[TEST 3] Category 2: HARD_DECLINE (expired_card)...")
    sub_hard_id = f"sub_demo_hard_{uuid.uuid4().hex[:6]}"
    hard_payload = build_payment_failed_payload(
        subscription_id=sub_hard_id,
        error_code="BAD_REQUEST_ERROR",
        error_description="Card has expired (expiry date 05/24 in past)",
        error_source="customer",
        error_step="payment_authentication",
        error_reason="expired_card"
    )
    res_hard = send_simulation_request(endpoint, hard_payload, webhook_secret)
    print(f"  HTTP Status: {res_hard.status_code}")
    res_hard_json = res_hard.json()
    print(f"  Decision:    {json.dumps(res_hard_json.get('decision'), indent=2)}")
    assert res_hard_json.get("decision", {}).get("decline_bucket") == "HARD_DECLINE"
    assert res_hard_json.get("decision", {}).get("decided_action") == "NUDGE_PAYMENT_UPDATE"
    print("  -> PASSED: Correctly classified as HARD_DECLINE -> NUDGE_PAYMENT_UPDATE.")

    # ------------------------------------------------------------------------
    # TEST 4: RISK_FLAG (payment_risk_check_failed) -> ESCALATE_TO_HUMAN
    # ------------------------------------------------------------------------
    print("\n[TEST 4] Category 3: RISK_FLAG (payment_risk_check_failed)...")
    sub_risk_id = f"sub_demo_risk_{uuid.uuid4().hex[:6]}"
    risk_payload = build_payment_failed_payload(
        subscription_id=sub_risk_id,
        error_code="BAD_REQUEST_ERROR",
        error_description="Transaction declined by card issuer risk check filters",
        error_source="gateway",
        error_step="payment_authorization",
        error_reason="payment_risk_check_failed"
    )
    res_risk = send_simulation_request(endpoint, risk_payload, webhook_secret)
    print(f"  HTTP Status: {res_risk.status_code}")
    res_risk_json = res_risk.json()
    print(f"  Decision:    {json.dumps(res_risk_json.get('decision'), indent=2)}")
    assert res_risk_json.get("decision", {}).get("decline_bucket") == "RISK_FLAG"
    assert res_risk_json.get("decision", {}).get("decided_action") == "ESCALATE_TO_HUMAN"
    print("  -> PASSED: Correctly classified as RISK_FLAG -> ESCALATE_TO_HUMAN.")

    # ------------------------------------------------------------------------
    # TEST 5: Global Stopping Rule (Blocking Attempt #4)
    # ------------------------------------------------------------------------
    print("\n[TEST 5] Global Stopping Rule: Simulating 4 Attempts on Soft Decline...")
    sub_stop_id = f"sub_demo_stop_{uuid.uuid4().hex[:6]}"
    for attempt in range(1, 4):
        p = build_payment_failed_payload(subscription_id=sub_stop_id, error_reason="insufficient_funds")
        r = send_simulation_request(endpoint, p, webhook_secret)
        print(f"  Attempt #{attempt}: Action = {r.json().get('decision', {}).get('decided_action')}, Attempt Count = {r.json().get('decision', {}).get('attempt_number')}")

    # 4th attempt: should hit stopping rule
    p4 = build_payment_failed_payload(subscription_id=sub_stop_id, error_reason="insufficient_funds")
    r4 = send_simulation_request(endpoint, p4, webhook_secret)
    d4 = r4.json().get("decision", {})
    print(f"  Attempt #4: Action = {d4.get('decided_action')}, State = {d4.get('lifecycle_state')}")
    print(f"  Reasoning:  {d4.get('reasoning')}")
    assert d4.get("lifecycle_state") == "STOPPED_MAX_ATTEMPTS"
    print("  -> PASSED: Stopping rule successfully halted automated retries at attempt #4.")

    # ------------------------------------------------------------------------
    # TEST 6: Replay Webhook Idempotency (Already-Terminal Subscription)
    # ------------------------------------------------------------------------
    print("\n[TEST 6] Replay Test: Sending duplicate webhook for already-stopped subscription...")
    res_replay = send_simulation_request(endpoint, p4, webhook_secret)
    d_replay = res_replay.json().get("decision", {})
    print(f"  Replay Action: {d_replay.get('decided_action')}")
    print(f"  Reasoning:     {d_replay.get('reasoning')}")
    assert d_replay.get("decided_action") == "NO_ACTION_ALREADY_STOPPED"
    print("  -> PASSED: Duplicate webhook ignored by global stopping rule without re-triggering.")

    # ------------------------------------------------------------------------
    # Query Decision Audit Trail
    # ------------------------------------------------------------------------
    print("\n[AUDIT] Querying Decision Audit Trail via /audit/decisions...")
    audit_res = requests.get(f"{base_url}/audit/decisions?limit=6")
    audit_data = audit_res.json()
    print(f"  Total decision rows retrieved: {audit_data.get('count')}")
    print(f"  Sample decision log entries:\n{json.dumps(audit_data.get('decisions', [])[:2], indent=2)}")

    print("\n" + "=" * 75)
    print("PHASE 2 SIMULATION COMPLETED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    run_full_simulation(base_url=url)
