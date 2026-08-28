-- ============================================================================
-- Razorpay Subscription Recovery Agent - Database Schema (Supabase / Postgres)
-- ============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Table: webhook_events (PHASE 1)
-- Purpose: Unprocessed, append-only raw webhook audit log.
-- Every incoming Razorpay webhook is captured here with complete payload fidelity
-- before any classifier or recovery policy touches it.
-- ============================================================================
CREATE TABLE IF NOT EXISTS webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id TEXT,                                 -- Razorpay X-Razorpay-Event-Id header or payload event ID
    event_type VARCHAR(100) NOT NULL,              -- e.g., 'subscription.pending', 'subscription.halted', 'payment.failed'
    payload JSONB NOT NULL,                        -- Complete raw unmodified JSON payload
    headers JSONB DEFAULT '{}'::jsonb,             -- Webhook HTTP headers (signature, event id, user agent)
    signature_valid BOOLEAN NOT NULL DEFAULT false,-- Whether cryptographic HMAC-SHA256 signature passed verification
    processing_status VARCHAR(50) DEFAULT 'unprocessed', -- 'unprocessed', 'classified', 'action_taken', 'ignored'
    error_reason TEXT,                             -- Reason if parsing/processing failed
    received_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_event_type ON webhook_events (event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_events_received_at ON webhook_events (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_events_signature_valid ON webhook_events (signature_valid);
CREATE INDEX IF NOT EXISTS idx_webhook_events_subscription_id ON webhook_events USING gin ((payload -> 'payload' -> 'subscription' -> 'entity' -> 'id'));
CREATE INDEX IF NOT EXISTS idx_webhook_events_payment_id ON webhook_events USING gin ((payload -> 'payload' -> 'payment' -> 'entity' -> 'id'));

-- ============================================================================
-- Table: subscription_recovery_state (PHASE 2)
-- Purpose: Tracks current lifecycle state and attempt count per subscription
-- to strictly enforce stopping rules, replay idempotency, and state persistence.
-- ============================================================================
CREATE TABLE IF NOT EXISTS subscription_recovery_state (
    subscription_id VARCHAR(100) PRIMARY KEY,
    current_attempt_count INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE_RECOVERY', -- 'ACTIVE_RECOVERY', 'STOPPED_MAX_ATTEMPTS', 'ESCALATED_HUMAN_REVIEW', 'AWAITING_CUSTOMER_UPDATE', 'RESOLVED'
    last_event_id TEXT,
    last_payment_id TEXT,
    last_bucket VARCHAR(50),
    last_action VARCHAR(100),
    is_terminal BOOLEAN NOT NULL DEFAULT false,           -- True if max attempts reached or human escalation required
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_sub_recovery_status ON subscription_recovery_state (status);
CREATE INDEX IF NOT EXISTS idx_sub_recovery_is_terminal ON subscription_recovery_state (is_terminal);

-- ============================================================================
-- Table: recovery_audit_log (PHASE 2)
-- Purpose: Immutable decision audit log for decline classification & policy choices.
-- Tracks every automated reasoning step without executing actions.
-- ============================================================================
CREATE TABLE IF NOT EXISTS recovery_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id TEXT,                                      -- Source webhook event ID
    subscription_id VARCHAR(100) NOT NULL,              -- Target subscription
    payment_id VARCHAR(100),                            -- Associated payment entity ID
    decline_bucket VARCHAR(50) NOT NULL,               -- 'SOFT_DECLINE', 'HARD_DECLINE', 'RISK_FLAG'
    reasoning TEXT NOT NULL,                            -- Exact deterministic rationale for classification
    decided_action VARCHAR(100) NOT NULL,               -- 'SCHEDULE_RETRY', 'NUDGE_PAYMENT_UPDATE', 'ESCALATE_TO_HUMAN', 'NO_ACTION_ALREADY_STOPPED'
    attempt_number INT NOT NULL DEFAULT 1,              -- Attempt count at decision time
    retry_delay_seconds INT,                            -- Retry backoff delay (if applicable)
    subscription_lifecycle_state VARCHAR(50) NOT NULL,  -- Resulting state of the subscription
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_audit_subscription_id ON recovery_audit_log (subscription_id);
CREATE INDEX IF NOT EXISTS idx_audit_decline_bucket ON recovery_audit_log (decline_bucket);
CREATE INDEX IF NOT EXISTS idx_audit_decided_action ON recovery_audit_log (decided_action);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON recovery_audit_log (created_at DESC);

-- Enable RLS
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscription_recovery_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE recovery_audit_log ENABLE ROW LEVEL SECURITY;

-- Policies for service role full access
CREATE POLICY IF NOT EXISTS "Service role full access on webhook_events"
    ON webhook_events FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Service role full access on subscription_recovery_state"
    ON subscription_recovery_state FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Service role full access on recovery_audit_log"
    ON recovery_audit_log FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Policies for authenticated read-only access (for reporting/dashboards)
CREATE POLICY IF NOT EXISTS "Authenticated users can read webhook_events"
    ON webhook_events FOR SELECT TO authenticated USING (true);

CREATE POLICY IF NOT EXISTS "Authenticated users can read subscription_recovery_state"
    ON subscription_recovery_state FOR SELECT TO authenticated USING (true);

CREATE POLICY IF NOT EXISTS "Authenticated users can read recovery_audit_log"
    ON recovery_audit_log FOR SELECT TO authenticated USING (true);
