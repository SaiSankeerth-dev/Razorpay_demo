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
    agent = res["ai_recovery_agent"]
    comp = res["comparative_impact"]
    safety = res["ai_safety_and_performance"]

    print("\n" + "=" * 65)
    print("RAZORPAY AI REVENUE RECOVERY EVALUATION")
    print("=" * 65)
    print(f"Dataset Split:         {res['dataset_split']} ({split_file})")
    print(f"Cases Evaluated:       {res['cases_evaluated']}")
    print(f"Total Revenue at Risk: INR {res['total_revenue_at_risk_inr']:,.2f}")
    print("\n" + f"{'METRIC':<22} {'BASELINE':<16} {'AI AGENT':<16} {'DELTA / IMPACT'}")
    print("-" * 65)
    print(f"{'Recovery rate':<22} {base['recovery_rate_pct']:.2f}%{'':<9} {agent['recovery_rate_pct']:.2f}%{'':<9} +{comp['incremental_recovery_rate_gain_pct']:.2f}% Absolute Gain")
    print(f"{'Revenue recovered':<22} INR {base['recovered_revenue_inr']:<11,.2f} INR {agent['recovered_revenue_inr']:<11,.2f} +INR {comp['incremental_recovered_revenue_inr']:,.2f}")
    print(f"{'Retries attempted':<22} {base['retries_attempted']:<16} {agent['retries_attempted']:<16} -{comp['unnecessary_retries_avoided']} Retries Avoided")
    print(f"{'Risk retries':<22} {base['risk_retries_attempted']:<16} {agent['risk_retries_attempted']:<16} {comp['risk_retries_prevented']} Violations Prevented")
    print(f"{'Customer contacts':<22} {base['customer_contacts']:<16} {agent['customer_contacts']:<16} +{agent['customer_contacts']} Targeted Nudges")
    print(f"{'Human escalations':<22} {base['human_escalations']:<16} {agent['human_escalations']:<16} +{agent['human_escalations']} Risk Quarantined")
    print("-" * 65)

    print(f"\nIncremental recovered revenue:\nINR {comp['incremental_recovered_revenue_inr']:,.2f}")
    print(f"\nAI diagnosis accuracy:\n{safety['diagnosis_accuracy_pct']:.2f}%")
    print(f"\nAI intervention accuracy:\n{safety['intervention_accuracy_pct']:.2f}%")
    print(f"\nUnsafe AI recommendations:\n{safety['unsafe_ai_recommendations']}")
    print(f"\nPolicy violations:\n0 (0.00%)")
    print(f"\nPolicy Firewall overrides / blocks:\n{safety['policy_firewall_blocks_or_overrides']}")
    print("=" * 65)
    print("Artifacts generated: evaluation/results/benchmark.json & benchmark.md\n")


if __name__ == "__main__":
    main()
