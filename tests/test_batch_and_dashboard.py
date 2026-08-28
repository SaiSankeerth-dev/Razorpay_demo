"""
Tests for Phase 4: Batch Dataset Pipeline, Dashboard Metrics, Arithmetic Consistency & Drill-down Timeline.
"""
import pytest
from db.repository import (
    clear_local_store,
    get_dashboard_metrics,
    get_dashboard_bucket_breakdown,
    get_dashboard_exceptions,
    get_subscription_timeline
)
from scripts.generate_batch_data import generate_and_run_batch


@pytest.fixture(autouse=True)
def run_batch():
    clear_local_store()
    generate_and_run_batch(clean_first=True)
    yield
    clear_local_store()


def test_batch_dataset_realistic_distribution():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Verify 50+ subscriptions generated with a realistic decline mix:
    ~50% Soft Declines (30/60), ~25% Risk Flags (15/60), ~25% Hard Declines (15/60).
    """
    metrics = get_dashboard_metrics()
    breakdown = get_dashboard_bucket_breakdown()

    assert metrics["total_subscriptions_evaluated"] == 60
    assert breakdown["SOFT_DECLINE"]["total_count"] == 30
    assert breakdown["RISK_FLAG"]["total_count"] == 15
    assert breakdown["HARD_DECLINE"]["total_count"] == 15


def test_recovery_rate_arithmetic_consistency():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Verify recovery rate number is internally consistent:
    (recovered / total_failing) * 100 exactly equals the displayed percentage.
    And verify the rate is realistic (20% - 50%), not suspiciously >90%.
    """
    metrics = get_dashboard_metrics()

    failing_amt = metrics["total_failing_amount_inr"]
    recovered_amt = metrics["total_recovered_amount_inr"]
    displayed_pct = metrics["recovery_rate_pct"]

    assert failing_amt > 0
    assert recovered_amt > 0

    # Strict arithmetic check
    expected_pct = round((recovered_amt / failing_amt) * 100.0, 2)
    assert displayed_pct == expected_pct

    # Realistic rate check: 20% to 50%
    assert 20.0 <= displayed_pct <= 50.0
    assert displayed_pct < 90.0, "Suspiciously high recovery rate (>90%) rejected"


def test_exceptions_list_populated_honestly():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Verify exceptions list is populated with real unresolved cases:
    - Retries exhausted (STOPPED_MAX_ATTEMPTS)
    - Risk flags (ESCALATED_HUMAN_REVIEW)
    - DND holds
    - Opt-outs
    - Lifetime caps
    """
    exceptions = get_dashboard_exceptions()
    assert len(exceptions) >= 25, "Exceptions queue must not be suspiciously small"

    categories = {ex["exception_type"] for ex in exceptions}
    assert "SECURITY_RISK_ESCALATION" in categories
    assert "DND_HOURS_HOLD" in categories or "MAX_RETRIES_EXHAUSTED" in categories


def test_drill_down_timeline_continuity():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Verify drill-down works on a real subscription, returning full decision-to-outcome timeline.
    """
    timeline = get_subscription_timeline("sub_soft_001")
    assert timeline["subscription_id"] == "sub_soft_001"
    assert timeline["total_audit_events"] >= 1

    audit_entry = timeline["audit_timeline"][0]
    assert audit_entry["subscription_id"] == "sub_soft_001"
    assert audit_entry["decline_bucket"] == "SOFT_DECLINE"
    assert audit_entry["action_executed"] == "RETRY_PAYMENT"
    assert audit_entry["action_result"] == "SUCCESS"
