"""
CLI Script for Simulating Customer Reply Channel (Phase 3).
Allows simulating customer promise-to-pay commitments and opt-out requests.
"""
import sys
import os
import argparse
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.executors.promise_to_pay_executor import (
    record_customer_promise,
    evaluate_and_check_in_promise
)
from db.repository import opt_out_subscription, get_all_promise_to_pay, get_subscription_recovery_state


def main():
    parser = argparse.ArgumentParser(description="Simulate Customer Reply Channel")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Promise to pay command
    p_promise = subparsers.add_parser("promise", help="Log a customer promise to pay")
    p_promise.add_argument("subscription_id", help="Subscription ID")
    p_promise.add_argument("promised_date", help="Promised payment date (YYYY-MM-DD)")
    p_promise.add_argument("--notes", default="Customer promised payment", help="Notes")

    # Check promise command
    p_check = subparsers.add_parser("check-promise", help="Evaluate promise-to-pay check-in")
    p_check.add_argument("subscription_id", help="Subscription ID")
    p_check.add_argument("--date", default=None, help="Current date to simulate (YYYY-MM-DD)")

    # Opt out command
    p_opt = subparsers.add_parser("opt-out", help="Opt out subscription from notifications")
    p_opt.add_argument("subscription_id", help="Subscription ID")

    args = parser.parse_args()

    if args.command == "promise":
        record = record_customer_promise(
            subscription_id=args.subscription_id,
            promised_date=args.promised_date,
            notes=args.notes
        )
        print("=== PROMISE TO PAY RECORDED ===")
        print(json.dumps(record, indent=2))

    elif args.command == "check-promise":
        result = evaluate_and_check_in_promise(
            subscription_id=args.subscription_id,
            current_date=args.date
        )
        print("=== PROMISE CHECK-IN RESULT ===")
        print(json.dumps(result, indent=2))

    elif args.command == "opt-out":
        state = opt_out_subscription(args.subscription_id)
        print("=== SUBSCRIPTION OPTED OUT ===")
        print(json.dumps(state, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
