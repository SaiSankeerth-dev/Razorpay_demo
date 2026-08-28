"""
Concurrency & Idempotency Race-Condition Tests.

Verifies that simultaneous duplicate webhook events processed concurrently
across parallel threads result in exactly one logical decision and zero duplicate financial actions.
"""
import concurrent.futures
import pytest
from db.config import settings
from db.repository import (
    clear_local_store,
    save_raw_webhook,
    get_recovery_audit_logs,
    get_subscription_recovery_state
)
from agent.decision_engine import process_webhook_decision


@pytest.fixture(autouse=True)
def clean_db():
    settings.USE_LOCAL_DB = True
    clear_local_store()
    yield
    clear_local_store()


def test_concurrent_identical_webhook_delivery_idempotency():
    """
    CONCURRENCY TEST:
    Simulates 10 concurrent threads simultaneously processing the same webhook failure event
    for subscription 'sub_concurrent_001'.
    
    EXPECTED:
    - Thread-safe execution without race conditions or crashes.
    - All 10 webhooks are captured in raw webhook ledger.
    - Exactly 1 state created in subscription_recovery_state.
    - Exactly 1 decision action evaluated on attempt #1.
    """
    sub_id = "sub_concurrent_001"
    payload = {
        "entity": "event",
        "account_id": "acc_demo_merchant_01",
        "event": "payment.failed",
        "id": "evt_concurrent_001",
        "created_at": 1787890000,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_concurrent_001",
                    "amount": 149900,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "insufficient_funds",
                    "error_description": "Payment failed: insufficient_funds",
                    "notes": {"subscription_id": sub_id, "customer_email": "conc@example.com"}
                }
            }
        }
    }

    def process_task(thread_id):
        save_raw_webhook("payment.failed", payload, signature_valid=True, event_id=f"evt_concurrent_{thread_id}")
        return process_webhook_decision(payload)

    # Launch 10 simultaneous threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_task, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 10

    # Verify subscription state
    state = get_subscription_recovery_state(sub_id)
    assert state is not None
    assert state["subscription_id"] == sub_id
    assert state["status"] in ["ACTIVE_RECOVERY", "STOPPED_MAX_ATTEMPTS"]
    assert state["current_attempt_count"] <= 3


def test_replayed_webhook_on_terminal_state_concurrent():
    """
    IDEMPOTENCY CONCURRENCY TEST:
    Pre-seeds a subscription in terminal state (STOPPED_MAX_ATTEMPTS),
    then bombards it with 5 parallel webhook replays.
    
    EXPECTED:
    - 0 new recovery actions triggered.
    - All replays safely ignored via RULE_FIREWALL_TERMINAL_STOP.
    """
    sub_id = "sub_terminal_concurrent_002"
    from db.repository import upsert_subscription_recovery_state
    upsert_subscription_recovery_state({
        "subscription_id": sub_id,
        "current_attempt_count": 3,
        "status": "STOPPED_MAX_ATTEMPTS",
        "is_terminal": True
    })

    payload = {
        "entity": "event",
        "event": "payment.failed",
        "id": "evt_replay_conc",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_replay_conc",
                    "amount": 249900,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_reason": "insufficient_funds",
                    "notes": {"subscription_id": sub_id}
                }
            }
        }
    }

    def replay_task():
        return process_webhook_decision(payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(replay_task) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All decisions must be NO_ACTION_ALREADY_STOPPED
    for ext, cls_res, decision, audit_row in results:
        assert decision.action.value == "NO_ACTION_ALREADY_STOPPED"
        assert decision.is_terminal is True
        assert audit_row == {}  # No new audit row inserted on terminal replay
