"""
Tests for Promise-to-Pay Commitment Tracking & Exactly-Once Check-in Enforcement (Phase 3).
"""
import pytest
from db.repository import clear_local_store, get_all_promise_to_pay
from agent.executors.promise_to_pay_executor import (
    record_customer_promise,
    evaluate_and_check_in_promise
)


@pytest.fixture(autouse=True)
def clean_db():
    clear_local_store()
    yield
    clear_local_store()


def test_promise_to_pay_full_lifecycle():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove that a promise-to-pay record is logged with a future date,
    checked in exactly ONCE on or after that date, and a second check-in
    never fires before payment status re-evaluation.
    """
    sub_id = "sub_promise_test_505"
    promised_date = "2026-09-05"

    # Step 1: Record promise to pay
    record = record_customer_promise(
        subscription_id=sub_id,
        promised_date=promised_date,
        notes="Customer confirmed via email reply they will pay on Sep 5th"
    )
    assert record["subscription_id"] == sub_id
    assert record["promised_date"] == promised_date
    assert record["status"] == "PENDING"
    assert record["check_in_count"] == 0

    # Step 2: Check before promised date (e.g. 2026-09-01) -> Held
    held_res = evaluate_and_check_in_promise(
        subscription_id=sub_id,
        current_date="2026-09-01"
    )
    assert held_res["checked_in"] is False
    assert "in future" in held_res["reason"]

    # Step 3: Check on promised date (2026-09-05) -> First Check-in Fires!
    checkin_1 = evaluate_and_check_in_promise(
        subscription_id=sub_id,
        current_date="2026-09-05"
    )
    assert checkin_1["checked_in"] is True
    assert checkin_1["check_in_count"] == 1
    assert checkin_1["status"] == "CHECKED_IN"

    # Step 4: Second check-in attempt on the same day/after (2026-09-06) -> STRICTLY BLOCKED!
    checkin_2 = evaluate_and_check_in_promise(
        subscription_id=sub_id,
        current_date="2026-09-06"
    )
    assert checkin_2["checked_in"] is False
    assert "already checked in once" in checkin_2["reason"].lower()
    assert "second automatic check-in forbidden" in checkin_2["reason"].lower()

    # Step 5: Verify persistent state in DB
    all_p = get_all_promise_to_pay(sub_id)
    assert len(all_p) == 1
    assert all_p[0]["check_in_count"] == 1
    assert all_p[0]["status"] == "CHECKED_IN"
