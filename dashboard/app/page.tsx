'use client';

import React, { useState, useEffect } from 'react';
import { 
  AlertTriangle, 
  CheckCircle2, 
  TrendingUp, 
  ShieldAlert, 
  RefreshCw, 
  Database, 
  Clock, 
  ExternalLink,
  X
} from 'lucide-react';

interface Metrics {
  total_subscriptions_evaluated: number;
  total_failing_amount_inr: number;
  total_recovered_amount_inr: number;
  recovery_rate_pct: number;
  recovered_subscriptions_count: number;
  unrecovered_subscriptions_count: number;
  underlying_queries: {
    total_failing_amount_query: string;
    total_recovered_amount_query: string;
    recovery_rate_formula: string;
    arithmetic_verification: string;
  };
}

interface BucketBreakdown {
  SOFT_DECLINE: {
    total_count: number;
    total_amount_inr: number;
    recovered_count: number;
    recovered_amount_inr: number;
    unresolved_count: number;
  };
  HARD_DECLINE: {
    total_count: number;
    total_amount_inr: number;
    actions: { NUDGE_SENT: number; HELD_DND: number; BLOCKED_OPT_OUT: number; BLOCKED_LIFETIME_CAP: number };
  };
  RISK_FLAG: {
    total_count: number;
    total_amount_inr: number;
    actions: { ESCALATE_TO_HUMAN: number };
  };
}

interface ExceptionItem {
  subscription_id: string;
  decline_bucket: string;
  amount_inr: number;
  exception_type: string;
  severity: string;
  reasoning: string;
  action_executed: string;
  action_result: string;
  logged_at: string;
}

export default function RecoveryDashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [breakdown, setBreakdown] = useState<BucketBreakdown | null>(null);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [selectedSub, setSelectedSub] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  async function fetchData() {
    setLoading(true);
    try {
      const [mRes, bRes, eRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/dashboard/metrics`),
        fetch(`${API_BASE}/api/v1/dashboard/bucket-breakdown`),
        fetch(`${API_BASE}/api/v1/dashboard/exceptions`)
      ]);
      setMetrics(await mRes.json());
      setBreakdown(await bRes.json());
      const eData = await eRes.json();
      setExceptions(eData.exceptions || []);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  }

  async function openTimeline(subId: string) {
    setSelectedSub(subId);
    try {
      const res = await fetch(`${API_BASE}/api/v1/dashboard/subscriptions/${subId}/timeline`);
      const data = await res.json();
      setTimeline(data.audit_timeline || []);
    } catch (err) {
      console.error('Failed to load timeline:', err);
    }
  }

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8 space-y-8 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-3">
            <span className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-sm font-black">RZ</span>
            Razorpay Subscription Payment Recovery Dashboard
          </h1>
          <p className="text-xs text-slate-400 mt-1">Live Decline Classification, Dunning Guardrails & Financial Audit Metrics</p>
        </div>
        <button 
          onClick={fetchData} 
          className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-xs border border-slate-700 text-slate-300"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </header>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold mb-2">
            <span>TOTAL AT-RISK ARR</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            ₹{metrics?.total_failing_amount_inr?.toLocaleString('en-IN', { minimumFractionDigits: 2 }) || '0.00'}
          </div>
          <div className="text-xs text-slate-500 mt-2">{metrics?.total_subscriptions_evaluated || 0} subscriptions evaluated</div>
        </div>

        <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-5">
          <div className="flex items-center justify-between text-emerald-400 text-xs font-semibold mb-2">
            <span>TOTAL ₹ RECOVERED</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">
            ₹{metrics?.total_recovered_amount_inr?.toLocaleString('en-IN', { minimumFractionDigits: 2 }) || '0.00'}
          </div>
          <div className="text-xs text-slate-500 mt-2">{metrics?.recovered_subscriptions_count || 0} soft retries succeeded</div>
        </div>

        <div className="bg-slate-900 border border-cyan-500/30 rounded-xl p-5">
          <div className="flex items-center justify-between text-cyan-400 text-xs font-semibold mb-2">
            <span>RECOVERY RATE</span>
            <TrendingUp className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-cyan-300 font-mono">
            {metrics?.recovery_rate_pct?.toFixed(2) || '0.00'}%
          </div>
          <div className="text-xs text-slate-500 mt-2">Recovered ÷ Total Failing</div>
        </div>

        <div className="bg-slate-900 border border-rose-500/30 rounded-xl p-5">
          <div className="flex items-center justify-between text-rose-400 text-xs font-semibold mb-2">
            <span>EXCEPTIONS QUEUE</span>
            <ShieldAlert className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold text-rose-400 font-mono">
            {metrics?.unrecovered_subscriptions_count || 0}
          </div>
          <div className="text-xs text-slate-500 mt-2">Unresolved / Escalated Cases</div>
        </div>
      </div>

      {/* Query Inspector */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
        <h2 className="text-xs font-bold text-slate-300 uppercase flex items-center gap-2">
          <Database className="w-4 h-4 text-blue-400" /> Audit Query & Arithmetic Formula Proof
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="bg-slate-950 p-3 rounded border border-slate-800">
            <span className="text-slate-400 font-semibold block mb-1">Headline Query (Total Recovered ₹):</span>
            <code className="text-emerald-400 font-mono text-[11px] block">{metrics?.underlying_queries?.total_recovered_amount_query}</code>
          </div>
          <div className="bg-slate-950 p-3 rounded border border-slate-800">
            <span className="text-slate-400 font-semibold block mb-1">Arithmetic Verification:</span>
            <code className="text-cyan-300 font-mono text-[11px] block">{metrics?.underlying_queries?.arithmetic_verification}</code>
          </div>
        </div>
      </div>

      {/* Exceptions Workbench */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-white uppercase flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-400" /> Exceptions & Unresolved Cases Workbench
          </h2>
          <span className="text-xs px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30">
            {exceptions.length} Cases
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase">
                <th className="py-2.5 px-3">Subscription</th>
                <th className="py-2.5 px-3">Bucket</th>
                <th className="py-2.5 px-3">Amount</th>
                <th className="py-2.5 px-3">Category</th>
                <th className="py-2.5 px-3">Reasoning</th>
                <th className="py-2.5 px-3 text-right">Drill Down</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {exceptions.map((ex) => (
                <tr key={ex.subscription_id} className="hover:bg-slate-800/40">
                  <td className="py-2.5 px-3 text-white font-medium">{ex.subscription_id}</td>
                  <td className="py-2.5 px-3">{ex.decline_bucket}</td>
                  <td className="py-2.5 px-3 text-slate-200">₹{ex.amount_inr.toFixed(2)}</td>
                  <td className="py-2.5 px-3 text-amber-400">{ex.exception_type}</td>
                  <td className="py-2.5 px-3 text-slate-400 truncate max-w-xs font-sans">{ex.reasoning}</td>
                  <td className="py-2.5 px-3 text-right">
                    <button 
                      onClick={() => openTimeline(ex.subscription_id)}
                      className="px-2 py-1 rounded bg-blue-600/20 text-blue-400 border border-blue-500/30 hover:bg-blue-600/30"
                    >
                      Audit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Timeline Modal */}
      {selectedSub && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-6 space-y-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Clock className="w-4 h-4 text-cyan-400" /> Audit Timeline: {selectedSub}
              </h3>
              <button onClick={() => setSelectedSub(null)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3">
              {timeline.map((item, idx) => (
                <div key={idx} className="bg-slate-950 p-3 rounded border border-slate-800 text-xs space-y-1">
                  <div className="flex items-center justify-between font-bold text-white">
                    <span>{item.decided_action}</span>
                    <span className="text-slate-500 font-mono text-[10px]">{item.created_at}</span>
                  </div>
                  <p className="text-slate-400">{item.reasoning}</p>
                  <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-800 flex justify-between">
                    <span>Action: {item.action_executed}</span>
                    <span className="text-emerald-400">Result: {item.action_result}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
