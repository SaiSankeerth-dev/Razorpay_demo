"""
Naive Fixed-Schedule Retry Baseline.

Represents conventional dumb billing recovery:
- Fixed 24-hour retry interval.
- Retries all payment failures blindly up to 3 times.
- Zero decline awareness (retries expired cards, deleted tokens, and fraud/risk flags).
- Zero customer self-serve payment update nudges.
"""
from typing import Dict, Any, List


class NaiveRetryBaseline:
    """
    Naive baseline simulator.
    Evaluates a dataset of payment failures using dumb fixed-schedule retries.
    """

    @classmethod
    def evaluate_scenario(cls, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates naive recovery on a single scenario.
        """
        category = scenario.get("category")
        amt_inr = scenario.get("amount_inr", 0.0)
        is_recoverable = scenario.get("is_recoverable_via_retry", False)
        attempt_recovered = scenario.get("attempt_recovered_on")

        # Naive behavior: Always retry up to 3 times
        total_retries = 3
        risk_retries = 0
        customer_contacts = 0
        human_escalations = 0
        recovered = False

        if category == "RISK_FLAG":
            # Naive baseline blindly retries fraud/risk declines -> Violates security
            risk_retries = 3
            recovered = False
        elif category == "HARD_DECLINE":
            # Naive baseline blindly retries expired cards -> 0% recovery, 0 nudges sent
            risk_retries = 0
            recovered = False
        elif category == "SOFT_DECLINE":
            # Transient soft decline: recovers if recoverable
            risk_retries = 0
            if is_recoverable and attempt_recovered is not None:
                total_retries = attempt_recovered
                recovered = True
            else:
                total_retries = 3
                recovered = False

        return {
            "scenario_id": scenario["scenario_id"],
            "subscription_id": scenario["subscription_id"],
            "amount_inr": amt_inr,
            "recovered": recovered,
            "recovered_amount_inr": amt_inr if recovered else 0.0,
            "retries_attempted": total_retries,
            "risk_retries_attempted": risk_retries,
            "customer_contacts": customer_contacts,
            "human_escalations": human_escalations,
            "unnecessary_retries": 3 if category in ["HARD_DECLINE", "RISK_FLAG"] or (category == "SOFT_DECLINE" and not is_recoverable) else (total_retries - (attempt_recovered or 0))
        }

    @classmethod
    def evaluate_dataset(cls, scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluates an entire dataset against the Naive Baseline."""
        results = [cls.evaluate_scenario(s) for s in scenarios]
        total_failing_inr = sum(s["amount_inr"] for s in scenarios)
        total_recovered_inr = sum(r["recovered_amount_inr"] for r in results)
        total_retries = sum(r["retries_attempted"] for r in results)
        total_risk_retries = sum(r["risk_retries_attempted"] for r in results)
        recovered_count = sum(1 for r in results if r["recovered"])

        recovery_rate = (total_recovered_inr / total_failing_inr * 100.0) if total_failing_inr > 0 else 0.0

        return {
            "model": "Naive Fixed-Schedule Retry Baseline",
            "total_cases": len(scenarios),
            "total_failing_inr": round(total_failing_inr, 2),
            "total_recovered_inr": round(total_recovered_inr, 2),
            "recovery_rate_pct": round(recovery_rate, 2),
            "recovered_count": recovered_count,
            "total_retries_attempted": total_retries,
            "risk_retries_attempted": total_risk_retries,
            "customer_contacts": 0,
            "human_escalations": 0
        }
