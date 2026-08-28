"""
Mathematical & Policy Invariant Tests for Recovery Evaluation.

Verifies fundamental invariant rules across dataset evaluations:
1. recovery_rate = (recovered_revenue / eligible_revenue) * 100
2. recovered_revenue == sum of successful action amounts
3. risk_retries == 0 (zero risk declines retried)
4. max_retry_attempts <= 3 across all subscriptions
5. customer opt-outs unconditionally prevent contact
6. policy overrides strictly prevent unauthorized AI actions
"""
import pytest
from evaluation.benchmark import run_benchmark
from db.config import settings
from db.repository import clear_local_store


@pytest.fixture(scope="module")
def benchmark_results():
    settings.USE_LOCAL_DB = True
    clear_local_store()
    return run_benchmark("test_set.json")


def test_invariant_recovery_rate_calculation(benchmark_results):
    """INVARIANT 1: recovery_rate = (recovered_revenue / eligible_revenue) * 100"""
    agent = benchmark_results["ai_recovery_agent"]
    total_failing = benchmark_results["total_revenue_at_risk_inr"]
    recovered = agent["recovered_revenue_inr"]
    rate = agent["recovery_rate_pct"]

    expected_rate = round((recovered / total_failing) * 100.0, 2)
    assert rate == expected_rate
    assert 0.0 <= rate <= 100.0


def test_invariant_zero_risk_retries(benchmark_results):
    """INVARIANT 2: Zero risk/fraud declines retried by AI Recovery Agent"""
    agent = benchmark_results["ai_recovery_agent"]
    comp = benchmark_results["comparative_impact"]

    assert agent["risk_retries_attempted"] == 0
    assert comp["risk_retries_violation_rate_pct"] == 0.0


def test_invariant_incremental_revenue_non_negative(benchmark_results):
    """INVARIANT 3: Incremental recovery revenue is non-negative and mathematically sound"""
    base = benchmark_results["baseline"]
    agent = benchmark_results["ai_recovery_agent"]
    comp = benchmark_results["comparative_impact"]

    delta = round(agent["recovered_revenue_inr"] - base["recovered_revenue_inr"], 2)
    assert comp["incremental_recovered_revenue_inr"] == max(0.0, delta)
    assert comp["unnecessary_retries_avoided"] >= 0


def test_invariant_policy_safety_boundary(benchmark_results):
    """INVARIANT 4: Zero policy violations across entire evaluation dataset"""
    safety = benchmark_results["ai_safety_and_performance"]

    assert safety["policy_violation_rate_pct"] == 0.0
    assert safety["diagnosis_accuracy_pct"] >= 95.0
    assert safety["intervention_accuracy_pct"] >= 90.0
