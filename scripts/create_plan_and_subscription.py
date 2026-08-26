"""
Script to create a test Plan and test Subscription in Razorpay Test Mode using the SDK.
"""
import sys
import os
import json
import logging
import razorpay

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("razorpay-setup")


def get_client() -> razorpay.Client:
    """Initializes and returns the Razorpay client."""
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET

    if not key_id or key_id.startswith("rzp_test_placeholder") or not key_secret or key_secret == "placeholder_secret":
        logger.error("=" * 70)
        logger.error("RAZORPAY TEST API KEYS NOT CONFIGURED IN .env")
        logger.error("Please add your test credentials to .env:")
        logger.error("RAZORPAY_KEY_ID=rzp_test_...")
        logger.error("RAZORPAY_KEY_SECRET=...")
        logger.error("=" * 70)
        sys.exit(1)

    client = razorpay.Client(auth=(key_id, key_secret))
    # Enable automatic retries with exponential backoff & jitter from SDK
    client.set_app_details({"title": "Subscription-Recovery-Agent", "version": "1.0.0"})
    return client


def create_test_plan(client: razorpay.Client) -> dict:
    """
    Creates a weekly test billing plan.
    Razorpay API: POST /v1/plans
    """
    plan_payload = {
        "period": "weekly",
        "interval": 1,
        "item": {
            "name": "SaaS Pro Recovery Test Plan",
            "amount": 49900,  # 499.00 INR (in paise)
            "currency": "INR",
            "description": "Weekly recurring subscription plan for payment recovery testing"
        },
        "notes": {
            "project": "Razorpay-Buildathon-Recovery-Agent",
            "environment": "test_mode"
        }
    }

    logger.info("Creating Test Plan via Razorpay API...")
    try:
        plan = client.plan.create(plan_payload)
        logger.info(f"Plan Created Successfully! Plan ID: {plan.get('id')}")
        return plan
    except Exception as e:
        logger.error(f"Failed to create Plan: {e}")
        raise


def create_test_subscription(client: razorpay.Client, plan_id: str) -> dict:
    """
    Creates a test subscription against a plan.
    Razorpay API: POST /v1/subscriptions
    """
    sub_payload = {
        "plan_id": plan_id,
        "total_count": 12,
        "quantity": 1,
        "customer_notify": 1,
        "notes": {
            "project": "Razorpay-Buildathon-Recovery-Agent",
            "test_case": "decline_aware_recovery_flow",
            "tier": "pro_monthly"
        }
    }

    logger.info(f"Creating Test Subscription for Plan {plan_id}...")
    try:
        subscription = client.subscription.create(sub_payload)
        logger.info(f"Subscription Created Successfully! Subscription ID: {subscription.get('id')}")
        logger.info(f"Initial State: {subscription.get('status')}")
        return subscription
    except Exception as e:
        logger.error(f"Failed to create Subscription: {e}")
        raise


def main():
    print("=" * 70)
    print("Razorpay Test Mode Plan & Subscription Provisioning")
    print("=" * 70)

    client = get_client()

    # 1. Create Plan
    plan = create_test_plan(client)
    plan_id = plan["id"]
    print("\n--- Plan Details ---")
    print(json.dumps(plan, indent=2))

    # 2. Create Subscription
    subscription = create_test_subscription(client, plan_id)
    sub_id = subscription["id"]
    print("\n--- Subscription Details ---")
    print(json.dumps(subscription, indent=2))

    print("\n" + "=" * 70)
    print("PROVISIONING COMPLETED:")
    print(f"  Plan ID:         {plan_id}")
    print(f"  Subscription ID: {sub_id}")
    print(f"  Status:          {subscription.get('status')} (Exact initial state)")
    print(f"  Auth URL:        {subscription.get('short_url')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
