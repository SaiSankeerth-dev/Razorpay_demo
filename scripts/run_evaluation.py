"""
One-Command Evaluation Runner for Razorpay AI Revenue Recovery Agent.

Executes the full benchmark evaluation over the held-out test dataset (150 cases),
computes exact baseline vs AI agent comparisons, and outputs clean formatted results.
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evaluation.benchmark import run_benchmark


def main():
    split_file = sys.argv[1] if len(sys.argv) > 1 else "test_set.json"
    res = run_benchmark(split_file)

    base = res["baseline"]
    rules = res["rules_only"]
    agent = res["ai_recovery_agent"]
    comp = res["comparative_impact"]
    safety = res["ai_safety_and_performance"]

    print("\n" + "=" * 60)
    print("RECOVERX BENCHMARK")
    print("=" * 60)
    print(f"\nRevenue at Risk: INR {res['total_revenue_at_risk_inr']:,.2f} ({res['cases_evaluated']} scenarios, {res['dataset_split']})")
    
    print("\nNAIVE BASELINE")
    print(f"Recovery Rate:      {base['recovery_rate_pct']:.2f}%")
    print(f"Revenue Recovered:  INR {base['recovered_revenue_inr']:,.2f}")
    print(f"Retries:            {base['retries_attempted']}")
    print(f"Risk Retries:       {base['risk_retries_attempted']} (VIOLATIONS)")

    print("\nRULES ONLY")
    print(f"Recovery Rate:      {rules['recovery_rate_pct']:.2f}%")
    print(f"Revenue Recovered:  INR {rules['recovered_revenue_inr']:,.2f}")
    print(f"Retries:            {rules['retries_attempted']}")
    print(f"Risk Retries:       {rules['risk_retries_attempted']}")

    print("\nAI + POLICY FIREWALL")
    print(f"Recovery Rate:      {agent['recovery_rate_pct']:.2f}%")
    print(f"Revenue Recovered:  INR {agent['recovered_revenue_inr']:,.2f}")
    print(f"Retries:            {agent['retries_attempted']}")
    print(f"Risk Retries:       {agent['risk_retries_attempted']}")

    print("\nAI VALUE")
    print(f"Incremental Revenue vs Baseline:    +INR {comp['incremental_recovered_revenue_vs_baseline_inr']:,.2f} (+{comp['incremental_recovery_gain_vs_baseline_pct']:.2f}pp)")
    print(f"Incremental Revenue vs Rules-Only:  +INR {comp['incremental_recovered_revenue_vs_rules_inr']:,.2f} (+{comp['incremental_recovery_gain_vs_rules_pct']:.2f}pp)")
    print(f"Recovery Improvement vs Baseline:   +{comp['incremental_recovery_gain_vs_baseline_pct']:.2f}pp")
    print(f"Retries Avoided:                    {comp['unnecessary_retries_avoided']}")

    print("\nAI QUALITY")
    print(f"Diagnosis Accuracy:       {safety['diagnosis_accuracy_pct']:.2f}%")
    print(f"Intervention Accuracy:    {safety['intervention_accuracy_pct']:.2f}%")
    print(f"Unsafe Recommendations:   {safety['unsafe_ai_recommendations']}")
    print(f"Policy Blocks:            {safety['policy_firewall_blocks_or_overrides']}")

    print("\nSAFETY")
    print(f"Executed Unsafe Actions:  {safety['unsafe_ai_recommendations']} (Policy Violation Rate: {safety['policy_violation_rate_pct']:.2f}%)")
    print("=" * 60)
    print("Results saved to: evaluation/results/benchmark.json\n")


if __name__ == "__main__":
    main()
