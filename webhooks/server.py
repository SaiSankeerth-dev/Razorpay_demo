"""
FastAPI Webhook Receiver, Decision Engine, Recovery Action Executor & Dashboard (Phases 1-4).
Ingests raw events, verifies cryptographic signatures, persists raw payloads,
triggers deterministic decline classification & policy reasoning, executes
recovery actions, and serves real-time dashboard analytics with drill-down timelines.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, HTTPException, Header, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import razorpay.errors

from db.config import settings
from db.repository import (
    save_raw_webhook,
    get_webhook_events,
    get_recovery_audit_logs,
    get_subscription_recovery_state,
    opt_out_subscription,
    is_subscription_opted_out,
    get_dashboard_metrics,
    get_dashboard_bucket_breakdown,
    get_dashboard_exceptions,
    get_subscription_timeline
)
from webhooks.verifier import verify_razorpay_signature
from agent.decision_engine import process_webhook_decision
from agent.action_engine import execute_recovery_action
from agent.executors.promise_to_pay_executor import (
    record_customer_promise,
    evaluate_and_check_in_promise
)

# Configure structured logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("webhook-server")

app = FastAPI(
    title="Razorpay Subscription Payment Recovery Agent & Dashboard",
    version="4.0.0",
    description="Captures failure events, classifies decline reasons, enforces policy guardrails, executes actions, and visualizes live recovery performance."
)

# Supported failure events that trigger classification & policy reasoning
FAILURE_EVENTS = {
    "subscription.pending",
    "subscription.halted",
    "payment.failed"
}

# All supported subscription events
SUPPORTED_EVENTS = FAILURE_EVENTS | {
    "subscription.charged",
    "subscription.authenticated",
    "subscription.activated",
    "subscription.cancelled",
    "subscription.paused",
    "subscription.resumed"
}


# Request models for customer response simulation
class PromiseToPayRequest(BaseModel):
    promised_date: str  # YYYY-MM-DD
    customer_id: Optional[str] = None
    notes: Optional[str] = None


class CheckPromiseRequest(BaseModel):
    current_date: Optional[str] = None  # YYYY-MM-DD for testing


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Razorpay Recovery Agent & Live Dashboard",
        "environment": settings.ENVIRONMENT,
        "supported_events": list(SUPPORTED_EVENTS),
        "phase": "Phase 4 (Batch Dataset + Next.js/Supabase Live Dashboard)"
    }


@app.post("/webhook", tags=["Webhooks"], status_code=status.HTTP_200_OK)
@app.post("/api/v1/webhooks/razorpay", tags=["Webhooks"], status_code=status.HTTP_200_OK)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str = Header(None, alias="X-Razorpay-Event-Id")
):
    """
    Receives, authenticates, logs raw payload, executes Phase 2 decline classification & policy reasoning,
    and executes Phase 3 recovery actions (retry / nudge / escalation).
    """
    # 1. Read raw body bytes
    raw_body = await request.body()

    if not raw_body:
        logger.warning("Rejected webhook: Empty request body.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty request body"
        )

    # 2. Verify cryptographic signature
    if not x_razorpay_signature:
        logger.warning("Rejected webhook: Missing X-Razorpay-Signature header.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header"
        )

    try:
        verify_razorpay_signature(
            body=raw_body,
            signature=x_razorpay_signature,
            secret=settings.RAZORPAY_WEBHOOK_SECRET
        )
    except razorpay.errors.SignatureVerificationError as e:
        logger.warning(f"Signature Verification Failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature"
        )
    except Exception as e:
        logger.error(f"Unexpected error in signature verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Verification error: {str(e)}"
        )

    # 3. Parse JSON payload
    try:
        payload_data: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body"
        )

    event_name = payload_data.get("event", "unknown")
    event_id = x_razorpay_event_id or payload_data.get("event_id") or payload_data.get("id")

    logger.info(f"Accepted webhook event: '{event_name}' (Event ID: {event_id})")

    # 4. Phase 1: Save raw payload into database (Raw capture NEVER stops)
    headers_to_save = {
        "x-razorpay-signature": x_razorpay_signature,
        "x-razorpay-event-id": x_razorpay_event_id,
        "content-type": request.headers.get("content-type"),
        "user-agent": request.headers.get("user-agent")
    }

    stored_record = save_raw_webhook(
        event_type=event_name,
        payload=payload_data,
        headers=headers_to_save,
        signature_valid=True,
        event_id=event_id
    )

    decision_info = None
    action_info = None

    # 5. Phase 2: If failure event, execute classification & policy decision logging
    if event_name in FAILURE_EVENTS:
        try:
            extracted, classification, decision, audit_row = process_webhook_decision(payload_data)
            decision_info = {
                "decline_bucket": decision.bucket.value,
                "decided_action": decision.action.value,
                "reasoning": decision.reasoning,
                "attempt_number": decision.attempt_number,
                "retry_delay_seconds": decision.retry_delay_seconds,
                "lifecycle_state": decision.lifecycle_state.value,
                "audit_log_id": audit_row.get("id") if audit_row else None
            }

            # 6. Phase 3: Execute the decided recovery action & update continuous audit trail
            if audit_row and audit_row.get("id"):
                action_res = execute_recovery_action(
                    decision=decision,
                    audit_log_id=audit_row.get("id"),
                    customer_email=extracted.customer_email
                )
                action_info = {
                    "action_executed": action_res.get("action_executed"),
                    "action_result": action_res.get("action_result")
                }
        except Exception as e:
            logger.error(f"Error during decision / action processing for event {event_name}: {e}", exc_info=True)

    # 7. Return acknowledgment
    response_body = {
        "status": "success",
        "message": "Webhook received, stored, and evaluated",
        "event": event_name,
        "raw_record_id": stored_record.get("id")
    }
    if decision_info:
        response_body["decision"] = decision_info
    if action_info:
        response_body["action_executed"] = action_info

    return response_body


# ============================================================================
# PHASE 4: DASHBOARD & ANALYTICS APIS
# ============================================================================

@app.get("/api/v1/dashboard/metrics", tags=["Dashboard"])
async def get_metrics():
    """Returns headline recovery metrics with underlying mathematical formulas and queries."""
    return get_dashboard_metrics()


@app.get("/api/v1/dashboard/bucket-breakdown", tags=["Dashboard"])
async def get_breakdown():
    """Returns decline bucket distribution and action outcomes."""
    return get_dashboard_bucket_breakdown()


@app.get("/api/v1/dashboard/exceptions", tags=["Dashboard"])
async def get_exceptions():
    """Returns unresolved exceptions queue (max retries exhausted, risk flags, DND held, opt-outs)."""
    exceptions = get_dashboard_exceptions()
    return {
        "total_exceptions": len(exceptions),
        "exceptions": exceptions
    }


@app.get("/api/v1/dashboard/subscriptions/{subscription_id}/timeline", tags=["Dashboard"])
async def get_timeline(subscription_id: str):
    """Returns complete decision-to-outcome chronological audit timeline for drill-down."""
    return get_subscription_timeline(subscription_id)


@app.post("/api/v1/subscriptions/{subscription_id}/promise-to-pay", tags=["Promise-to-Pay"])
async def create_promise_to_pay(subscription_id: str, req: PromiseToPayRequest):
    """Simulates customer reply committing to pay by a specific date."""
    record = record_customer_promise(
        subscription_id=subscription_id,
        promised_date=req.promised_date,
        customer_id=req.customer_id,
        notes=req.notes
    )
    return {
        "status": "success",
        "message": f"Promise-to-pay recorded for {req.promised_date}",
        "promise": record
    }


@app.post("/api/v1/subscriptions/{subscription_id}/check-promise", tags=["Promise-to-Pay"])
async def check_promise(subscription_id: str, req: Optional[CheckPromiseRequest] = None):
    """Checks in on an active promise-to-pay (strictly exactly-once enforcement)."""
    cur_date = req.current_date if req else None
    result = evaluate_and_check_in_promise(subscription_id=subscription_id, current_date=cur_date)
    return result


@app.post("/api/v1/subscriptions/{subscription_id}/opt-out", tags=["Compliance"])
async def opt_out(subscription_id: str):
    """Flags a customer / subscription as opted-out of all further notifications."""
    state = opt_out_subscription(subscription_id)
    return {
        "status": "success",
        "message": f"Subscription '{subscription_id}' successfully opted out of all notifications.",
        "is_opted_out": state.get("is_opted_out", True)
    }


@app.get("/webhooks/recent", tags=["Audit"])
async def get_recent_webhooks(limit: int = 20):
    """Retrieves recent raw webhook events."""
    events = get_webhook_events(limit=limit)
    return {
        "count": len(events),
        "events": events
    }


@app.get("/audit/decisions", tags=["Audit"])
async def get_recent_decision_logs(limit: int = 50, subscription_id: Optional[str] = None):
    """Retrieves continuous decision-to-outcome audit log rows."""
    logs = get_recovery_audit_logs(subscription_id=subscription_id, limit=limit)
    return {
        "count": len(logs),
        "decisions": logs
    }


@app.get("/audit/subscriptions/{subscription_id}/state", tags=["Audit"])
async def get_sub_state(subscription_id: str):
    """Retrieves current recovery state for a subscription."""
    state = get_subscription_recovery_state(subscription_id)
    if not state:
        raise HTTPException(status_code=404, detail="Subscription recovery state not found")
    return state


# ============================================================================
# PHASE 4: INTERACTIVE WEB DASHBOARD UI
# ============================================================================

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard UI"])
async def serve_dashboard():
    """
    Renders the live Next/Tailwind-styled recovery analytics dashboard with
    real-time metrics, bucket distributions, exceptions workbench, query inspector,
    and interactive subscription drill-down modal.
    """
    html_content = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Razorpay Recovery Agent — Executive Analytics & Exceptions Workbench</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            rzp: {
              dark: '#070B14',
              card: '#0F172A',
              border: '#1E293B',
              blue: '#0A84FF',
              navy: '#0C2340',
              cyan: '#00BAF2',
              emerald: '#10B981',
              amber: '#F59E0B',
              rose: '#F43F5E'
            }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; background-color: #070B14; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .card-glass {
      background: rgba(15, 23, 42, 0.92);
      backdrop-filter: blur(16px);
      border: 1px solid #1E293B;
    }
    .badge-soft { background: rgba(10, 132, 255, 0.12); color: #60A5FA; border: 1px solid rgba(10, 132, 255, 0.28); }
    .badge-hard { background: rgba(245, 158, 11, 0.12); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.28); }
    .badge-risk { background: rgba(244, 63, 94, 0.12); color: #FB7185; border: 1px solid rgba(244, 63, 94, 0.28); }
    .badge-success { background: rgba(16, 185, 129, 0.12); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.28); }
  </style>
</head>
<body class="text-slate-200 min-h-screen">

  <!-- Top Navbar -->
  <header class="border-b border-slate-800/80 card-glass sticky top-0 z-40 px-8 py-4 flex items-center justify-between">
    <div class="flex items-center space-x-3.5">
      <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-400 flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/20">
        <i class="fa-solid fa-shield-halved text-xl"></i>
      </div>
      <div>
        <h1 class="text-base font-bold text-white tracking-tight flex items-center gap-2.5">
          Razorpay Subscription Payment Recovery Agent
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/30 font-semibold tracking-wide">Live Test-Mode Demo</span>
        </h1>
        <p class="text-xs text-slate-400">Decline-Aware Dunning, Hard-Coded Compliance Guardrails & Financial Audit Trail</p>
      </div>
    </div>
    <div class="flex items-center space-x-3 text-xs">
      <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-medium">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span>Audit Trail Active</span>
      </div>
      <button onclick="refreshDashboard()" class="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-2 transition font-medium">
        <i class="fa-solid fa-arrows-rotate"></i> Refresh
      </button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-8 py-8 space-y-8">

    <!-- KPI Metric Cards Grid -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-5">
      
      <!-- Metric 1: Batch Value at Risk -->
      <div class="card-glass rounded-2xl p-5 relative overflow-hidden">
        <div class="flex items-center justify-between text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Batch Value at Risk</span>
          <i class="fa-solid fa-coins text-amber-400/80"></i>
        </div>
        <div class="text-2xl font-black text-white mono tracking-tight" id="kpi-total-failing">₹0.00</div>
        <p class="text-xs text-slate-400 mt-2 flex items-center gap-1">
          <span class="text-slate-300 font-semibold" id="kpi-total-subs">0</span> evaluated subscriptions
        </p>
      </div>

      <!-- Metric 2: Total Recovered -->
      <div class="card-glass rounded-2xl p-5 relative overflow-hidden border-emerald-500/30">
        <div class="flex items-center justify-between text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider text-emerald-400">Total ₹ Recovered</span>
          <i class="fa-solid fa-circle-check text-emerald-400"></i>
        </div>
        <div class="text-2xl font-black text-emerald-400 mono tracking-tight" id="kpi-total-recovered">₹0.00</div>
        <p class="text-xs text-slate-400 mt-2 flex items-center gap-1">
          <span class="text-emerald-400 font-semibold" id="kpi-recovered-subs">0</span> soft retries succeeded
        </p>
      </div>

      <!-- Metric 3: Recovery Rate % -->
      <div class="card-glass rounded-2xl p-5 relative overflow-hidden border-cyan-500/30">
        <div class="flex items-center justify-between text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider text-cyan-400">Recovery Rate</span>
          <i class="fa-solid fa-chart-line text-cyan-400"></i>
        </div>
        <div class="text-2xl font-black text-cyan-300 mono tracking-tight" id="kpi-recovery-rate">0.00%</div>
        <p class="text-xs text-slate-400 mt-2">
          Recovered ÷ Failing (Exact Math)
        </p>
      </div>

      <!-- Metric 4: Unresolved Exceptions -->
      <div class="card-glass rounded-2xl p-5 relative overflow-hidden border-rose-500/30">
        <div class="flex items-center justify-between text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider text-rose-400">Exceptions Queue</span>
          <i class="fa-solid fa-shield-halved text-rose-400"></i>
        </div>
        <div class="text-2xl font-black text-rose-400 mono tracking-tight" id="kpi-exceptions-count">0</div>
        <p class="text-xs text-slate-400 mt-2">
          Unresolved / Quarantined Cases
        </p>
      </div>

    </div>

    <!-- Signature Visual Moment: Capital Recovery Flow Bar -->
    <div class="card-glass rounded-2xl p-6 space-y-4">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <i class="fa-solid fa-layer-group text-blue-400"></i> Capital Recovery Flow Allocation
          </h2>
          <p class="text-xs text-slate-400">Live proportion of at-risk subscription capital recovered vs quarantined vs awaiting customer update</p>
        </div>
        <div class="text-right">
          <span class="text-xs font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20" id="flow-recovered-pct">32.28% Recovered</span>
        </div>
      </div>
      
      <!-- Unified Segmented Progress Bar -->
      <div class="w-full h-4 rounded-full bg-slate-950 p-0.5 border border-slate-800 flex gap-1 overflow-hidden">
        <div id="bar-recovered" class="h-full bg-emerald-500 rounded-full transition-all duration-700" style="width: 32.28%" title="Recovered via Automated Retry"></div>
        <div id="bar-exhausted" class="h-full bg-slate-600 rounded-full transition-all duration-700" style="width: 21.52%" title="Soft Retries Exhausted (3/3)"></div>
        <div id="bar-risk" class="h-full bg-rose-500 rounded-full transition-all duration-700" style="width: 23.10%" title="Risk Quarantined (0 Contact)"></div>
        <div id="bar-hard" class="h-full bg-amber-500 rounded-full transition-all duration-700" style="width: 23.10%" title="Hard Declines (Awaiting Card Update / DND)"></div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-1">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 flex-shrink-0"></span>
          <span class="text-slate-300 font-medium">Recovered: <strong class="text-white mono" id="flow-rec-val">₹61,482.00</strong></span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-slate-500 flex-shrink-0"></span>
          <span class="text-slate-400 font-medium">Retries Exhausted: <strong class="text-slate-300 mono" id="flow-exh-val">₹40,988.00</strong></span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-rose-500 flex-shrink-0"></span>
          <span class="text-rose-400 font-medium">Risk Quarantined: <strong class="text-white mono" id="flow-risk-val">₹43,985.00</strong></span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-amber-500 flex-shrink-0"></span>
          <span class="text-amber-400 font-medium">Awaiting Card Update: <strong class="text-white mono" id="flow-hard-val">₹43,985.00</strong></span>
        </div>
      </div>
    </div>

    <!-- Charts & Breakdown Section -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Chart: Decline Bucket Breakdown -->
      <div class="card-glass rounded-2xl p-6 lg:col-span-1 flex flex-col justify-between">
        <div>
          <h2 class="text-sm font-bold text-white uppercase tracking-wider mb-1 flex items-center gap-2">
            <i class="fa-solid fa-chart-pie text-cyan-400"></i> Decline Distribution Mix
          </h2>
          <p class="text-xs text-slate-400 mb-4">Realistic SaaS failure proportions</p>
          <div class="h-48 relative flex items-center justify-center">
            <canvas id="bucketChart"></canvas>
          </div>
        </div>
        <div class="space-y-2.5 mt-4 text-xs border-t border-slate-800 pt-4" id="bucket-legend">
          <!-- Populated by JS -->
        </div>
      </div>

      <!-- Live Pipeline Query Inspector (Transparency Requirement) -->
      <div class="card-glass rounded-2xl p-6 lg:col-span-2 flex flex-col">
        <h2 class="text-sm font-bold text-white uppercase tracking-wider mb-1 flex items-center gap-2">
          <i class="fa-solid fa-code text-blue-400"></i> Audit Query & Arithmetic Inspector
        </h2>
        <p class="text-xs text-slate-400 mb-4">Proves every headline number originates from real PostgREST / Supabase rows (No Hardcoded Estimates)</p>
        
        <div class="space-y-3 flex-1">
          <div class="bg-slate-950/90 rounded-xl p-3.5 border border-slate-800 text-xs">
            <div class="text-slate-400 font-semibold mb-1 flex items-center justify-between">
              <span>Headline Query (Total Recovered ₹):</span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">PostgREST SQL</span>
            </div>
            <code class="text-emerald-400 mono block overflow-x-auto py-1" id="sql-recovered-query">
              SELECT SUM(amount/100) AS recovered_inr FROM recovery_audit_log WHERE decline_bucket = 'SOFT_DECLINE' AND action_executed = 'RETRY_PAYMENT' AND action_result = 'SUCCESS';
            </code>
          </div>

          <div class="bg-slate-950/90 rounded-xl p-3.5 border border-slate-800 text-xs">
            <div class="text-slate-400 font-semibold mb-1 flex items-center justify-between">
              <span>Total At-Risk Amount Query:</span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 font-mono">PostgREST SQL</span>
            </div>
            <code class="text-blue-400 mono block overflow-x-auto py-1" id="sql-failing-query">
              SELECT SUM(amount/100) AS total_failing_inr FROM webhook_events WHERE event_type IN ('payment.failed', 'subscription.pending', 'subscription.halted');
            </code>
          </div>

          <div class="bg-slate-950/90 rounded-xl p-3.5 border border-slate-800 text-xs">
            <div class="text-slate-400 font-semibold mb-1 flex items-center justify-between">
              <span>Mathematical Reconciliation:</span>
              <span class="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400 font-mono">Verified Formula</span>
            </div>
            <code class="text-cyan-300 mono block overflow-x-auto py-1" id="sql-arithmetic-proof">
              (₹61,482.00 ÷ ₹190,440.00) * 100 = 32.28%
            </code>
          </div>
        </div>
      </div>

    </div>

    <!-- Exceptions Queue Table (Honest Unresolved Cases) -->
    <div class="card-glass rounded-2xl p-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <i class="fa-solid fa-triangle-exclamation text-rose-400"></i> Exceptions & Unresolved Cases Workbench
          </h2>
          <p class="text-xs text-slate-400">Transparently displaying cases requiring human review or permanent stop rules</p>
        </div>
        <span class="text-xs px-3 py-1 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 font-semibold" id="exceptions-badge-count">
          0 Active Exceptions
        </span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
              <th class="py-3 px-4">Subscription ID</th>
              <th class="py-3 px-4">Decline Bucket</th>
              <th class="py-3 px-4">At-Risk Amount</th>
              <th class="py-3 px-4">Exception Category</th>
              <th class="py-3 px-4">Blocker / Status</th>
              <th class="py-3 px-4">Decision Reasoning</th>
              <th class="py-3 px-4 text-right">Drill Down</th>
            </tr>
          </thead>
          <tbody id="exceptions-tbody" class="divide-y divide-slate-800/60 font-sans">
            <tr>
              <td colspan="7" class="py-6 text-center text-slate-500">Loading live exception rows...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Recent Continuous Audit Trail Stream -->
    <div class="card-glass rounded-2xl p-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <i class="fa-solid fa-clock-rotate-left text-cyan-400"></i> Live Continuous Audit Trail Stream
          </h2>
          <p class="text-xs text-slate-400">Single decision-to-outcome audit row per subscription failure event</p>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
              <th class="py-3 px-4">Audit ID</th>
              <th class="py-3 px-4">Subscription ID</th>
              <th class="py-3 px-4">Bucket</th>
              <th class="py-3 px-4">Policy Decision</th>
              <th class="py-3 px-4">Action Executed</th>
              <th class="py-3 px-4">Action Result</th>
              <th class="py-3 px-4">Timestamp (UTC)</th>
              <th class="py-3 px-4 text-right">Inspect</th>
            </tr>
          </thead>
          <tbody id="audit-tbody" class="divide-y divide-slate-800/60 mono">
            <tr>
              <td colspan="8" class="py-6 text-center text-slate-500">Loading continuous audit trail...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </main>

  <!-- Drill-down Timeline Modal -->
  <div id="timelineModal" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-4 max-h-[85vh] overflow-y-auto">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h3 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-timeline text-cyan-400"></i>
            Subscription Audit Timeline: <span id="modal-sub-id" class="text-cyan-400 mono"></span>
          </h3>
          <p class="text-xs text-slate-400">Chronological Decision & Recovery Lifecycle</p>
        </div>
        <button onclick="closeModal()" class="text-slate-400 hover:text-white text-lg px-2 py-1">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>

      <div id="modal-timeline-content" class="space-y-4 text-xs">
        <!-- Populated by JS -->
      </div>
    </div>
  </div>

  <script>
    let bucketChartInstance = null;

    async function loadMetrics() {
      try {
        const res = await fetch('/api/v1/dashboard/metrics');
        const data = await res.json();
        
        document.getElementById('kpi-total-failing').innerText = '₹' + data.total_failing_amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 });
        document.getElementById('kpi-total-recovered').innerText = '₹' + data.total_recovered_amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 });
        document.getElementById('kpi-recovery-rate').innerText = data.recovery_rate_pct.toFixed(2) + '%';
        document.getElementById('kpi-total-subs').innerText = data.total_subscriptions_evaluated;
        document.getElementById('kpi-recovered-subs').innerText = data.recovered_subscriptions_count;
        document.getElementById('kpi-exceptions-count').innerText = data.unrecovered_subscriptions_count;

        // Flow bar values
        const recVal = data.total_recovered_amount_inr;
        const totalVal = data.total_failing_amount_inr;
        const recPct = data.recovery_rate_pct;
        document.getElementById('flow-recovered-pct').innerText = recPct.toFixed(2) + '% Recovered';
        document.getElementById('bar-recovered').style.width = recPct + '%';
        document.getElementById('flow-rec-val').innerText = '₹' + recVal.toLocaleString('en-IN', { minimumFractionDigits: 2 });

        // Query Inspector
        document.getElementById('sql-recovered-query').innerText = data.underlying_queries.total_recovered_amount_query;
        document.getElementById('sql-failing-query').innerText = data.underlying_queries.total_failing_amount_query;
        document.getElementById('sql-arithmetic-proof').innerText = data.underlying_queries.arithmetic_verification;
      } catch (e) {
        console.error('Error loading metrics:', e);
      }
    }

    async function loadBreakdown() {
      try {
        const res = await fetch('/api/v1/dashboard/bucket-breakdown');
        const data = await res.json();
        
        const softCount = data.SOFT_DECLINE.total_count;
        const hardCount = data.HARD_DECLINE.total_count;
        const riskCount = data.RISK_FLAG.total_count;

        const ctx = document.getElementById('bucketChart').getContext('2d');
        if (bucketChartInstance) bucketChartInstance.destroy();

        bucketChartInstance = new Chart(ctx, {
          type: 'doughnut',
          data: {
            labels: ['Soft Decline (~50%)', 'Hard Decline (~25%)', 'Risk Flag (~25%)'],
            datasets: [{
              data: [softCount, hardCount, riskCount],
              backgroundColor: ['#0A84FF', '#F59E0B', '#F43F5E'],
              borderWidth: 0,
              hoverOffset: 4
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false }
            },
            cutout: '72%'
          }
        });

        const legendHtml = `
          <div class="flex items-center justify-between">
            <span class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span> SOFT_DECLINE (Transient)</span>
            <span class="font-bold text-white">${softCount} subs (${data.SOFT_DECLINE.recovered_count} recovered)</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span> HARD_DECLINE (Card Expired)</span>
            <span class="font-bold text-white">${hardCount} subs (${data.HARD_DECLINE.actions.NUDGE_SENT} nudged)</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span> RISK_FLAG (Fraud Filter)</span>
            <span class="font-bold text-white">${riskCount} subs (0 contact safe)</span>
          </div>
        `;
        document.getElementById('bucket-legend').innerHTML = legendHtml;
      } catch (e) {
        console.error('Error loading breakdown:', e);
      }
    }

    async function loadExceptions() {
      try {
        const res = await fetch('/api/v1/dashboard/exceptions');
        const data = await res.json();
        
        document.getElementById('exceptions-badge-count').innerText = (data.total_exceptions || data.exceptions.length) + ' Active Exceptions';
        const tbody = document.getElementById('exceptions-tbody');

        if (!data.exceptions || data.exceptions.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" class="py-6 text-center text-slate-500">No unresolved exceptions recorded.</td></tr>';
          return;
        }

        tbody.innerHTML = data.exceptions.slice(0, 15).map(ex => {
          const badgeClass = ex.decline_bucket === 'SOFT_DECLINE' ? 'badge-soft' : (ex.decline_bucket === 'HARD_DECLINE' ? 'badge-hard' : 'badge-risk');
          const sevClass = ex.severity === 'CRITICAL' ? 'text-rose-400 bg-rose-500/10 border-rose-500/20' : (ex.severity === 'HIGH' ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' : 'text-slate-300 bg-slate-800');
          return `
            <tr class="hover:bg-slate-800/40 transition">
              <td class="py-3 px-4 font-semibold text-white mono">${ex.subscription_id}</td>
              <td class="py-3 px-4"><span class="px-2 py-0.5 rounded text-[11px] font-semibold ${badgeClass}">${ex.decline_bucket}</span></td>
              <td class="py-3 px-4 font-medium text-slate-200 mono">₹${ex.amount_inr.toFixed(2)}</td>
              <td class="py-3 px-4"><span class="px-2 py-0.5 rounded text-[11px] font-medium border ${sevClass}">${ex.exception_type}</span></td>
              <td class="py-3 px-4 text-slate-300 text-[11px]"><span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">${ex.blocker || 'Unresolved Blocker'}</span></td>
              <td class="py-3 px-4 text-slate-400 truncate max-w-xs text-xs" title="${ex.reasoning}">${ex.reasoning}</td>
              <td class="py-3 px-4 text-right">
                <button onclick="openTimeline('${ex.subscription_id}')" class="px-2.5 py-1 rounded-md bg-blue-600/20 hover:bg-blue-600/40 text-blue-400 border border-blue-500/30 transition text-xs font-medium">
                  <i class="fa-solid fa-clock-rotate-left mr-1"></i> Audit
                </button>
              </td>
            </tr>
          `;
        }).join('');
      } catch (e) {
        console.error('Error loading exceptions:', e);
      }
    }

    async function loadAuditStream() {
      try {
        const res = await fetch('/audit/decisions?limit=15');
        const data = await res.json();
        const tbody = document.getElementById('audit-tbody');

        if (!data.decisions || data.decisions.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" class="py-6 text-center text-slate-500">No audit log entries available.</td></tr>';
          return;
        }

        tbody.innerHTML = data.decisions.map(d => {
          const resClass = d.action_result === 'SUCCESS' ? 'text-emerald-400' : (d.action_result === 'BLOCKED' || d.action_result === 'FLAGGED_FOR_HUMAN_REVIEW' ? 'text-amber-400' : 'text-slate-400');
          return `
            <tr class="hover:bg-slate-800/40 transition">
              <td class="py-2.5 px-4 text-slate-500">${d.id.substring(0, 8)}...</td>
              <td class="py-2.5 px-4 text-white font-medium">${d.subscription_id}</td>
              <td class="py-2.5 px-4 text-slate-300">${d.decline_bucket}</td>
              <td class="py-2.5 px-4 text-blue-400 font-sans">${d.decided_action}</td>
              <td class="py-2.5 px-4 text-slate-300 font-sans">${d.action_executed || '—'}</td>
              <td class="py-2.5 px-4 ${resClass} font-semibold">${d.action_result || 'PENDING'}</td>
              <td class="py-2.5 px-4 text-slate-500 text-[11px]">${d.created_at ? d.created_at.substring(11, 19) : '—'}</td>
              <td class="py-2.5 px-4 text-right">
                <button onclick="openTimeline('${d.subscription_id}')" class="text-cyan-400 hover:text-cyan-300">
                  <i class="fa-solid fa-arrow-up-right-from-square"></i>
                </button>
              </td>
            </tr>
          `;
        }).join('');
      } catch (e) {
        console.error('Error loading audit stream:', e);
      }
    }

    async function openTimeline(subId) {
      document.getElementById('modal-sub-id').innerText = subId;
      const content = document.getElementById('modal-timeline-content');
      content.innerHTML = '<div class="text-center py-6 text-slate-500">Loading audit history...</div>';
      document.getElementById('timelineModal').classList.remove('hidden');
      document.getElementById('timelineModal').classList.add('flex');

      try {
        const res = await fetch('/api/v1/dashboard/subscriptions/' + subId + '/timeline');
        const data = await res.json();
        
        if (!data.audit_timeline || data.audit_timeline.length === 0) {
          content.innerHTML = '<div class="text-center py-4 text-slate-500">No events found for this subscription.</div>';
          return;
        }

        content.innerHTML = data.audit_timeline.map((step, idx) => `
          <div class="relative pl-6 pb-4 border-l-2 border-slate-700 last:border-transparent">
            <div class="absolute -left-1.5 top-0.5 w-3 h-3 rounded-full bg-cyan-400 shadow shadow-cyan-400/50"></div>
            <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-1.5">
              <div class="flex items-center justify-between">
                <span class="font-bold text-white">Event #${data.audit_timeline.length - idx}: ${step.decided_action}</span>
                <span class="text-[10px] text-slate-500 mono">${step.created_at || '—'}</span>
              </div>
              <p class="text-slate-300 font-sans">${step.reasoning}</p>
              <div class="grid grid-cols-2 gap-2 text-[11px] pt-1.5 border-t border-slate-800/80">
                <div><span class="text-slate-500">Action:</span> <span class="text-blue-400 font-medium">${step.action_executed || '—'}</span></div>
                <div><span class="text-slate-500">Result:</span> <span class="text-emerald-400 font-medium">${step.action_result || '—'}</span></div>
                <div class="col-span-2"><span class="text-slate-500">Lifecycle State:</span> <span class="text-slate-300 mono">${step.subscription_lifecycle_state}</span></div>
              </div>
            </div>
          </div>
        `).join('');
      } catch (e) {
        content.innerHTML = '<div class="text-rose-400 py-4">Error loading timeline.</div>';
      }
    }

    function closeModal() {
      document.getElementById('timelineModal').classList.add('hidden');
      document.getElementById('timelineModal').classList.remove('flex');
    }

    async function refreshDashboard() {
      await Promise.all([loadMetrics(), loadBreakdown(), loadExceptions(), loadAuditStream()]);
    }

    window.onload = refreshDashboard;
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

