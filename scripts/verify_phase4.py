"""
Phase 4 Verification Script.
Executes live verification for batch dataset, metrics arithmetic, underlying SQL queries,
exceptions workbench, and drill-down timeline.
"""
import sys
import os
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.config import settings
from db.repository import (
    clear_local_store,
    get_dashboard_metrics,
    get_dashboard_bucket_breakdown,
    get_dashboard_exceptions,
    get_subscription_timeline
)
from scripts.generate_batch_data import generate_and_run_batch

settings.USE_LOCAL_DB = True

print("=" * 80)
print("PHASE 4 ACCEPTANCE VERIFICATION RUNNER")
print("=" * 80)

# Run full batch pipeline
result = generate_and_run_batch(clean_first=True)
metrics = result["metrics"]
breakdown = result["breakdown"]
exceptions = result["exceptions"]

print("\n" + "-" * 80)
print("1. BATCH DATASET BREAKDOWN (50+ SUBSCRIPTIONS)")
print("-" * 80)
print(f"Total Subscriptions Evaluated: {metrics['total_subscriptions_evaluated']}")
print(json.dumps(breakdown, indent=2))

print("\n" + "-" * 80)
print("2. DASHBOARD HEADLINE METRICS & UNDERLYING QUERIES")
print("-" * 80)
print(json.dumps(metrics, indent=2))

print("\n" + "-" * 80)
print("3. EXCEPTIONS QUEUE (UNRESOLVED CASES)")
print("-" * 80)
print(f"Total Exceptions Count: {len(exceptions)}")
print("Sample Exception Rows (First 5):")
print(json.dumps(exceptions[:5], indent=2))

print("\n" + "-" * 80)
print("4. DRILL-DOWN TIMELINE (SAMPLE REAL SUBSCRIPTION)")
print("-" * 80)
timeline = get_subscription_timeline("sub_soft_001")
print(json.dumps(timeline, indent=2))

print("\n" + "-" * 80)
print("5. ARITHMETIC RECONCILIATION")
print("-" * 80)
failing = metrics["total_failing_amount_inr"]
recovered = metrics["total_recovered_amount_inr"]
rate = metrics["recovery_rate_pct"]
computed = round((recovered / failing) * 100.0, 2)
print(f"Total Failing Amount:   INR {failing:,.2f}")
print(f"Total Recovered Amount: INR {recovered:,.2f}")
print(f"Displayed Rate:         {rate}%")
print(f"Computed Rate:          ({recovered} / {failing}) * 100 = {computed}%")
print(f"Arithmetic Valid:       {rate == computed}")
