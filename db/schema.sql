-- ============================================================================
-- Razorpay Subscription Recovery Agent - Database Schema (Supabase / Postgres)
-- ============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: webhook_events
-- Purpose: Unprocessed, append-only raw webhook audit log.
-- Every incoming Razorpay webhook is captured here with complete payload fidelity
-- before any classifier or recovery policy touches it.
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

-- Indices for rapid querying and audit indexing
CREATE INDEX IF NOT EXISTS idx_webhook_events_event_type ON webhook_events (event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_events_received_at ON webhook_events (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_events_signature_valid ON webhook_events (signature_valid);
CREATE INDEX IF NOT EXISTS idx_webhook_events_subscription_id ON webhook_events USING gin ((payload -> 'payload' -> 'subscription' -> 'entity' -> 'id'));
CREATE INDEX IF NOT EXISTS idx_webhook_events_payment_id ON webhook_events USING gin ((payload -> 'payload' -> 'payment' -> 'entity' -> 'id'));

-- Comment for table documentation
COMMENT ON TABLE webhook_events IS 'Immutable raw audit log of all Razorpay webhook events for subscription payment recovery analysis';

-- Setup Row Level Security (RLS)
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY IF NOT EXISTS "Service role full access on webhook_events"
    ON webhook_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Allow authenticated read-only access (for dashboards/monitoring)
CREATE POLICY IF NOT EXISTS "Authenticated users can read webhook_events"
    ON webhook_events
    FOR SELECT
    TO authenticated
    USING (true);
