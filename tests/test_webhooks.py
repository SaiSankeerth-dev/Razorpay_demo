"""
Integration tests for FastAPI Webhook Receiver, Decline Classification, and Database Persistence.
"""
import json
import pytest
from fastapi.testclient import TestClient
from webhooks.server import app
from db.config import settings
from db.repository import (
    clear_local_store,
    get_webhook_events,
    get_latest_event_by_type,
    get_recovery_audit_logs,
    get_subscription_recovery_state
)
from scripts.simulate_webhook import (
    build_payment_failed_payload,
    build_subscription_pending_payload,
    build_subscription_halted_payload,
    compute_signature
)

client = TestClient(app)
TEST_SECRET = "test_webhook_secret_for_suite_12345"


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown before and after each test."""
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = TEST_SECRET
    clear_local_store()
    yield
    settings.RAZORPAY_WEBHOOK_SECRET = original_secret
    clear_local_store()


def test_health_check():
    """Verify server health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "subscription.pending" in data["supported_events"]
    assert "subscription.halted" in data["supported_events"]
    assert "payment.failed" in data["supported_events"]


def test_payment_failed_event_capture_and_decision():
    """Verify that a valid payment.failed webhook is authenticated, classified, and logged to audit trail."""
    payload = build_payment_failed_payload(
        subscription_id="sub_test_1001",
        plan_id="plan_test_1001",
        error_code="BAD_REQUEST_ERROR",
        error_description="Payment failed due to insufficient funds",
        error_reason="insufficient_funds"
    )
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    sig = compute_signature(payload_bytes, TEST_SECRET)

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": "evt_test_failed_001",
        "Content-Type": "application/json"
    }

    response = client.post("/webhook", content=payload_bytes, headers=headers)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "success"
    assert res_json["event"] == "payment.failed"
    assert "decision" in res_json
    assert res_json["decision"]["decline_bucket"] == "SOFT_DECLINE"
    assert res_json["decision"]["decided_action"] == "SCHEDULE_RETRY"

    # Verify DB storage - raw capture
    saved = get_latest_event_by_type("payment.failed")
    assert saved is not None
    assert saved["event_type"] == "payment.failed"
    assert saved["signature_valid"] is True

    # Verify DB storage - decision audit log
    audit_logs = get_recovery_audit_logs(subscription_id="sub_test_1001")
    assert len(audit_logs) >= 1
    latest_decision = audit_logs[0]
    assert latest_decision["decline_bucket"] == "SOFT_DECLINE"
    assert latest_decision["decided_action"] == "SCHEDULE_RETRY"
    assert latest_decision["attempt_number"] == 1


def test_subscription_pending_event_capture_and_decision():
    """Verify that a valid subscription.pending webhook is authenticated, classified, and logged."""
    payload = build_subscription_pending_payload(
        subscription_id="sub_test_pending_2002",
        plan_id="plan_test_2002"
    )
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    sig = compute_signature(payload_bytes, TEST_SECRET)

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": "evt_test_pending_002",
        "Content-Type": "application/json"
    }

    response = client.post("/webhook", content=payload_bytes, headers=headers)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "success"
    assert res_json["event"] == "subscription.pending"
    assert res_json["decision"]["decline_bucket"] == "SOFT_DECLINE"

    # Verify DB storage
    saved = get_latest_event_by_type("subscription.pending")
    assert saved is not None
    audit_logs = get_recovery_audit_logs(subscription_id="sub_test_pending_2002")
    assert len(audit_logs) >= 1


def test_subscription_halted_event_capture_and_decision():
    """Verify that a valid subscription.halted webhook is classified as HARD_DECLINE."""
    payload = build_subscription_halted_payload(
        subscription_id="sub_test_halted_3003",
        plan_id="plan_test_3003"
    )
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    sig = compute_signature(payload_bytes, TEST_SECRET)

    headers = {
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": "evt_test_halted_003",
        "Content-Type": "application/json"
    }

    response = client.post("/webhook", content=payload_bytes, headers=headers)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "success"
    assert res_json["event"] == "subscription.halted"
    assert res_json["decision"]["decline_bucket"] == "HARD_DECLINE"
    assert res_json["decision"]["decided_action"] == "NUDGE_PAYMENT_UPDATE"

    # Verify DB storage
    audit_logs = get_recovery_audit_logs(subscription_id="sub_test_halted_3003")
    assert len(audit_logs) >= 1
    assert audit_logs[0]["decline_bucket"] == "HARD_DECLINE"


def test_tampered_signature_rejected_by_receiver():
    """
    Verify that webhook receiver strictly rejects tampered payloads with HTTP 400.
    """
    payload = build_payment_failed_payload()
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    tampered_sig = "invalid_tampered_signature_9999999999999999999999999999999999999999"

    headers = {
        "X-Razorpay-Signature": tampered_sig,
        "X-Razorpay-Event-Id": "evt_tampered_test",
        "Content-Type": "application/json"
    }

    response = client.post("/webhook", content=payload_bytes, headers=headers)
    assert response.status_code == 400
    assert "Invalid webhook signature" in response.json()["detail"]

    # Verify NO invalid event was persisted
    events = get_webhook_events()
    assert len(events) == 0


def test_missing_signature_header_rejected():
    """Verify that request with missing X-Razorpay-Signature header is rejected with HTTP 400."""
    payload = build_payment_failed_payload()
    payload_bytes = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json"
    }

    response = client.post("/webhook", content=payload_bytes, headers=headers)
    assert response.status_code == 400
    assert "Missing X-Razorpay-Signature" in response.json()["detail"]


def test_empty_body_rejected():
    """Verify that empty request body is rejected with HTTP 400."""
    headers = {
        "X-Razorpay-Signature": "some_sig",
        "Content-Type": "application/json"
    }

    response = client.post("/webhook", content=b"", headers=headers)
    assert response.status_code == 400
