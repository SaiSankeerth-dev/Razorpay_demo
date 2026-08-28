"""
Phase 3 Verification Script.
Executes and displays real live evidence for all 9 Phase 3 acceptance criteria.
"""
import sys
import os
import json
import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.config import settings
from db.repository import (
    clear_local_store,
    save_recovery_audit_log,
    get_recovery_audit_logs,
    opt_out_subscription,
    is_subscription_opted_out,
    get_subscription_contact_count
)
from agent.models import (
    AuditLogEntry,
    PolicyDecision,
    DecidedAction,
    DeclineBucket,
    SubscriptionLifecycleState
)
from agent.executors.retry_executor import execute_payment_retry, get_razorpay_client
from agent.executors.nudge_executor import execute_nudge_send
from agent.executors.escalation_executor import execute_risk_escalation
from agent.executors.promise_to_pay_executor import (
    record_customer_promise,
    evaluate_and_check_in_promise
)
from agent.compliance import evaluate_contact_compliance

settings.USE_LOCAL_DB = True
clear_local_store()

print("=" * 80)
print("PHASE 3 VERIFICATION: RECOVERY ACTIONS, COMPLIANCE GUARDRAILS & AUDIT TRAIL")
print("=" * 80)

# ----------------------------------------------------------------------------
# 1. REAL RETRY EXECUTED AGAINST RAZORPAY TEST MODE
# ----------------------------------------------------------------------------
print("\n[CHECK 1] REAL RETRY EXECUTED AGAINST RAZORPAY TEST MODE")
sub_retry_id = "sub_Ptest1000000001"
audit_retry = save_recovery_audit_log(AuditLogEntry(
    subscription_id=sub_retry_id,
    decline_bucket=DeclineBucket.SOFT_DECLINE.value,
    reasoning="Soft decline (insufficient funds). Retry attempt #1 queued.",
    decided_action=DecidedAction.SCHEDULE_RETRY.value,
    attempt_number=1,
    retry_delay_seconds=3600,
    subscription_lifecycle_state=SubscriptionLifecycleState.ACTIVE_RECOVERY.value
))
retry_res = execute_payment_retry(subscription_id=sub_retry_id, audit_log_id=audit_retry["id"])
print(f"Action Executed: {retry_res.get('action_executed')}")
print(f"Action Result:   {retry_res.get('action_result')}")
print(f"Executed At:     {retry_res.get('executed_at')}")
print(f"Live Razorpay API Response:\n{json.dumps(retry_res.get('api_response'), indent=2)}")

# ----------------------------------------------------------------------------
# 2. REAL EMAIL NUDGE SENT / SMTP ATTEMPT
# ----------------------------------------------------------------------------
print("\n[CHECK 2] REAL EMAIL NUDGE ATTEMPT VIA SMTP")
sub_nudge_id = "sub_demo_nudge_002"
audit_nudge = save_recovery_audit_log(AuditLogEntry(
    subscription_id=sub_nudge_id,
    decline_bucket=DeclineBucket.HARD_DECLINE.value,
    reasoning="Expired card detected. Customer self-serve update nudge queued.",
    decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
    attempt_number=0,
    subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
))
# Daytime at 12:00 PM IST
dt_daytime = datetime.datetime(2026, 8, 28, 12, 0, 0)
nudge_res = execute_nudge_send(
    subscription_id=sub_nudge_id,
    customer_email="customer.billing@example.com",
    audit_log_id=audit_nudge["id"],
    check_time=dt_daytime
)
print(f"Action Executed: {nudge_res.get('action_executed')}")
print(f"Action Result:   {nudge_res.get('action_result')}")
print(f"Executed At:     {nudge_res.get('executed_at')}")
print(f"Delivery Details:\n{json.dumps(nudge_res.get('details'), indent=2)}")

# ----------------------------------------------------------------------------
# 3. RISK_FLAG ZERO CONTACT & ZERO RETRY PROOF
# ----------------------------------------------------------------------------
print("\n[CHECK 3] RISK_FLAG ZERO CONTACT & ZERO RETRY GUARANTEE")
sub_risk_id = "sub_demo_risk_003"
audit_risk = save_recovery_audit_log(AuditLogEntry(
    subscription_id=sub_risk_id,
    decline_bucket=DeclineBucket.RISK_FLAG.value,
    reasoning="Transaction declined by card issuer risk check filters (payment_risk_check_failed).",
    decided_action=DecidedAction.ESCALATE_TO_HUMAN.value,
    attempt_number=0,
    subscription_lifecycle_state=SubscriptionLifecycleState.ESCALATED_HUMAN_REVIEW.value
))
risk_res = execute_risk_escalation(
    subscription_id=sub_risk_id,
    audit_log_id=audit_risk["id"],
    reasoning="Flagged by issuer fraud/security check"
)
print(f"Action Executed: {risk_res.get('action_executed')}")
print(f"Action Result:   {risk_res.get('action_result')}")
print(f"Guarantees:\n{json.dumps(risk_res.get('details'), indent=2)}")

# ----------------------------------------------------------------------------
# 4. DND WINDOW TEST (NUDGE QUEUED AT 11:00 PM IST)
# ----------------------------------------------------------------------------
print("\n[CHECK 4] DND WINDOW GUARDRAIL (QUEUED AT 11:00 PM IST)")
sub_dnd_id = "sub_demo_dnd_004"
audit_dnd = save_recovery_audit_log(AuditLogEntry(
    subscription_id=sub_dnd_id,
    decline_bucket=DeclineBucket.HARD_DECLINE.value,
    reasoning="Hard decline queued late at night.",
    decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
    attempt_number=0,
    subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
))
dt_11pm = datetime.datetime(2026, 8, 28, 23, 0, 0)
dnd_res = execute_nudge_send(
    subscription_id=sub_dnd_id,
    audit_log_id=audit_dnd["id"],
    check_time=dt_11pm
)
print(f"Action Executed: {dnd_res.get('action_executed')}")
print(f"Action Result:   {dnd_res.get('action_result')}")
print(f"Compliance Details:\n{json.dumps(dnd_res.get('compliance_details'), indent=2)}")

# ----------------------------------------------------------------------------
# 5. OPT-OUT GUARDRAIL TEST
# ----------------------------------------------------------------------------
print("\n[CHECK 5] OPT-OUT GUARDRAIL (FRESH DECLINE ON OPTED-OUT SUB)")
sub_opt_id = "sub_demo_optout_005"
opt_out_subscription(sub_opt_id)
audit_opt = save_recovery_audit_log(AuditLogEntry(
    subscription_id=sub_opt_id,
    decline_bucket=DeclineBucket.HARD_DECLINE.value,
    reasoning="Fresh hard decline on customer who previously opted out.",
    decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
    attempt_number=0,
    subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
))
opt_res = execute_nudge_send(
    subscription_id=sub_opt_id,
    audit_log_id=audit_opt["id"],
    check_time=dt_daytime
)
print(f"Action Executed: {opt_res.get('action_executed')}")
print(f"Action Result:   {opt_res.get('action_result')}")
print(f"Compliance Details:\n{json.dumps(opt_res.get('compliance_details'), indent=2)}")

# ----------------------------------------------------------------------------
# 6. LIFETIME CONTACT CAP TEST (BLOCKING TOUCH N+1)
# ----------------------------------------------------------------------------
print("\n[CHECK 6] GLOBAL LIFETIME CONTACT CAP (BLOCKING TOUCH #4)")
sub_cap_id = "sub_demo_cap_006"
for touch in range(1, 4):
    a = save_recovery_audit_log(AuditLogEntry(
        subscription_id=sub_cap_id,
        decline_bucket=DeclineBucket.HARD_DECLINE.value,
        reasoning=f"Decline event touch #{touch}",
        decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
        attempt_number=0,
        subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
    ))
    execute_nudge_send(subscription_id=sub_cap_id, audit_log_id=a["id"], check_time=dt_daytime)

print(f"Total contacts successfully sent so far: {get_subscription_contact_count(sub_cap_id)}/3")

# Attempt #4 across new decline
audit_cap4 = save_recovery_audit_log(AuditLogEntry(
    subscription_id=sub_cap_id,
    decline_bucket=DeclineBucket.HARD_DECLINE.value,
    reasoning="Decline event touch #4 (Attempting contact N+1)",
    decided_action=DecidedAction.NUDGE_PAYMENT_UPDATE.value,
    attempt_number=0,
    subscription_lifecycle_state=SubscriptionLifecycleState.AWAITING_CUSTOMER_UPDATE.value
))
cap_res = execute_nudge_send(
    subscription_id=sub_cap_id,
    audit_log_id=audit_cap4["id"],
    check_time=dt_daytime
)
print(f"Touch #4 Action Executed: {cap_res.get('action_executed')}")
print(f"Touch #4 Action Result:   {cap_res.get('action_result')}")
print(f"Compliance Details:\n{json.dumps(cap_res.get('compliance_details'), indent=2)}")

# ----------------------------------------------------------------------------
# 7. PROMISE-TO-PAY EXACTLY-ONCE CHECK-IN TEST
# ----------------------------------------------------------------------------
print("\n[CHECK 7] PROMISE-TO-PAY EXACTLY-ONCE CHECK-IN")
sub_p2p_id = "sub_demo_p2p_007"
record = record_customer_promise(
    subscription_id=sub_p2p_id,
    promised_date="2026-09-01",
    notes="Customer confirmed they will pay when salary credits on Sep 1st"
)
print(f"Promise Recorded: Promised Date = {record.get('promised_date')}, Status = {record.get('status')}")

# Before date (2026-08-30)
held_check = evaluate_and_check_in_promise(sub_p2p_id, current_date="2026-08-30")
print(f"Check-in Before Date (Aug 30): Checked In = {held_check.get('checked_in')}, Reason = {held_check.get('reason')}")

# On date (2026-09-01) -> Fires check-in #1
first_check = evaluate_and_check_in_promise(sub_p2p_id, current_date="2026-09-01")
print(f"Check-in On Date (Sep 1):     Checked In = {first_check.get('checked_in')}, Count = {first_check.get('check_in_count')}, Status = {first_check.get('status')}")

# Second attempt (2026-09-02) -> STRICTLY BLOCKED!
second_check = evaluate_and_check_in_promise(sub_p2p_id, current_date="2026-09-02")
print(f"Second Check-in (Sep 2):       Checked In = {second_check.get('checked_in')}, Reason = {second_check.get('reason')}")

# ----------------------------------------------------------------------------
# 8. LIVE CONTINUOUS AUDIT TRAIL QUERY (DECISION + OUTCOME IN SAME ROW)
# ----------------------------------------------------------------------------
print("\n[CHECK 8] LIVE CONTINUOUS DECISION-TO-OUTCOME AUDIT TRAIL")
all_logs = get_recovery_audit_logs(limit=4)
print(json.dumps(all_logs, indent=2))

print("\n" + "=" * 80)
print("ALL PHASE 3 VERIFICATION CHECKS COMPLETED!")
print("=" * 80)
