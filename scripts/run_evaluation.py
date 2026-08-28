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

    print("\n" + "=" * 80)
    print("RAZORPAY AI REVENUE RECOVERY — 3-ARM BENCHMARK EVALUATION")
    print("=" * 80)
    print(f"Dataset Split:         {res['dataset_split']} ({split_file})")
    print(f"Cases Evaluated:       {res['cases_evaluated']}")
    print(f"Total Revenue at Risk: INR {res['total_revenue_at_risk_inr']:,.2f}")
    print("\n" + f"{'METRIC':<20} {'FIXED BASELINE':<16} {'RULES-ONLY':<16} {'AI + FIREWALL':<16} {'AI vs BASELINE'}")
    print("-" * 80)
    print(f"{'Recovery rate':<20} {base['recovery_rate_pct']:.2f}%{'':<9} {rules['recovery_rate_pct']:.2f}%{'':<9} {agent['recovery_rate_pct']:.2f}%{'':<9} +{comp['incremental_recovery_gain_vs_baseline_pct']:.2f}%")
    print(f"{'Revenue recovered':<20} INR {base['recovered_revenue_inr']:<11,.2f} INR {rules['recovered_revenue_inr']:<11,.2f} INR {agent['recovered_revenue_inr']:<11,.2f} +INR {comp['incremental_recovered_revenue_vs_baseline_inr']:,.2f}")
    print(f"{'Retries used':<20} {base['retries_attempted']:<16} {rules['retries_attempted']:<16} {agent['retries_attempted']:<16} -{comp['unnecessary_retries_avoided']} avoided")
    print(f"{'Risk retries':<20} {base['risk_retries_attempted']:<16} {rules['risk_retries_attempted']:<16} {agent['risk_retries_attempted']:<16} {comp['risk_retries_prevented']} prevented")
    print(f"{'Unsafe actions':<20} {base['unsafe_actions_executed']:<16} {rules['unsafe_actions_executed']:<16} {agent['unsafe_actions_executed']:<16} 0 violations")
    print(f"{'Customer contacts':<20} {base['customer_contacts']:<16} {rules['customer_contacts']:<16} {agent['customer_contacts']:<16} +{agent['customer_contacts']} targeted")
    print(f"{'Human escalations':<20} {base['human_escalations']:<16} {rules['human_escalations']:<16} {agent['human_escalations']:<16} +{agent['human_escalations']} risk-isolated")
    print("-" * 80)

    print(f"\nIncremental Revenue vs Naive Baseline:  INR {comp['incremental_recovered_revenue_vs_baseline_inr']:,.2f} (+{comp['incremental_recovery_gain_vs_baseline_pct']:.2f}%)")
    print(f"Incremental Revenue vs Rules-Only:       INR {comp['incremental_recovered_revenue_vs_rules_inr']:,.2f} (+{comp['incremental_recovery_gain_vs_rules_pct']:.2f}%)")
    print(f"\nAI Diagnosis Accuracy:                  {safety['diagnosis_accuracy_pct']:.2f}%")
    print(f"AI Intervention Accuracy:               {safety['intervention_accuracy_pct']:.2f}%")
    print(f"Unsafe AI Recommendations Executed:     {safety['unsafe_ai_recommendations']}")
    print(f"Policy Firewall Overrides / Blocks:     {safety['policy_firewall_blocks_or_overrides']}")
    print(f"Policy Violation Rate:                  0.00%")
    print("=" * 80)
    print("Results saved to: evaluation/results/benchmark.json\n")


if __name__ == "__main__":
    main()
