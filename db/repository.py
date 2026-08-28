"""
Database Repository for Webhook Events, Decline Recovery States, and Audit Logs.
Handles Supabase table reads/writes with in-memory fallback for local offline testing.
"""
import uuid
import datetime
import logging
from typing import Optional, Dict, Any, List, Union
from db.client import get_supabase_client

logger = logging.getLogger(__name__)

# In-memory stores for testing / offline fallback
_local_webhook_store: List[Dict[str, Any]] = []
_local_audit_log_store: List[Dict[str, Any]] = []
_local_subscription_states: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# RAW WEBHOOK LOGGING (PHASE 1)
# ============================================================================

def save_raw_webhook(
    event_type: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, Any]] = None,
    signature_valid: bool = True,
    event_id: Optional[str] = None
) -> Dict[str, Any]:
    """Persists raw unmodified webhook event."""
    record_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    record_data = {
        "id": record_id,
        "event_id": event_id or payload.get("event_id") or payload.get("id"),
        "event_type": event_type,
        "payload": payload,
        "headers": headers or {},
        "signature_valid": signature_valid,
        "processing_status": "unprocessed",
        "received_at": now_iso,
        "created_at": now_iso
    }

    supabase = get_supabase_client()
    if supabase:
        try:
            response = supabase.table("webhook_events").insert(record_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Recorded webhook event {event_type} (ID: {record_id}) in Supabase.")
                return response.data[0]
            return record_data
        except Exception as e:
            logger.error(f"Error inserting webhook into Supabase: {e}. Storing locally.")
            _local_webhook_store.append(record_data)
            return record_data
    else:
        _local_webhook_store.append(record_data)
        return record_data


def get_webhook_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves recent raw webhook events."""
    supabase = get_supabase_client()
    if supabase:
        try:
            response = supabase.table("webhook_events").select("*").order("received_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching webhooks from Supabase: {e}")
            return list(reversed(_local_webhook_store[-limit:]))
    return list(reversed(_local_webhook_store[-limit:]))


def get_latest_event_by_type(event_type: str) -> Optional[Dict[str, Any]]:
    """Retrieves latest event of a given type."""
    supabase = get_supabase_client()
    if supabase:
        try:
            response = (
                supabase.table("webhook_events")
                .select("*")
                .eq("event_type", event_type)
                .order("received_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
        except Exception as e:
            logger.error(f"Error querying event by type from Supabase: {e}")

    for event in reversed(_local_webhook_store):
        if event.get("event_type") == event_type:
            return event
    return None


# ============================================================================
# SUBSCRIPTION RECOVERY STATE (PHASE 2)
# ============================================================================

def get_subscription_recovery_state(subscription_id: str) -> Optional[Dict[str, Any]]:
    """Fetches the current recovery state and attempt count for a subscription."""
    supabase = get_supabase_client()
    if supabase:
        try:
            response = (
                supabase.table("subscription_recovery_state")
                .select("*")
                .eq("subscription_id", subscription_id)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
        except Exception as e:
            logger.error(f"Error querying subscription state from Supabase: {e}")

    return _local_subscription_states.get(subscription_id)


def upsert_subscription_recovery_state(state_data: Dict[str, Any]) -> Dict[str, Any]:
    """Inserts or updates the recovery state for a subscription."""
    subscription_id = state_data["subscription_id"]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state_data["updated_at"] = now_iso
    if "created_at" not in state_data:
        state_data["created_at"] = now_iso

    supabase = get_supabase_client()
    if supabase:
        try:
            response = (
                supabase.table("subscription_recovery_state")
                .upsert(state_data)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return response.data[0]
        except Exception as e:
            logger.error(f"Error upserting subscription state to Supabase: {e}")

    _local_subscription_states[subscription_id] = state_data
    return state_data


# ============================================================================
# RECOVERY DECISION AUDIT LOG (PHASE 2)
# ============================================================================

def save_recovery_audit_log(entry: Any) -> Dict[str, Any]:
    """
    Persists an immutable decision log entry for decline classification and policy choice.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if isinstance(entry, dict):
        record_id = entry.get("id") or str(uuid.uuid4())
        record_data = {
            "id": record_id,
            "event_id": entry.get("event_id"),
            "subscription_id": entry.get("subscription_id"),
            "payment_id": entry.get("payment_id"),
            "decline_bucket": entry.get("decline_bucket"),
            "reasoning": entry.get("reasoning"),
            "decided_action": entry.get("decided_action"),
            "attempt_number": entry.get("attempt_number", 1),
            "retry_delay_seconds": entry.get("retry_delay_seconds"),
            "subscription_lifecycle_state": entry.get("subscription_lifecycle_state"),
            "created_at": entry.get("created_at") or now_iso
        }
    else:
        record_id = getattr(entry, "id", None) or str(uuid.uuid4())
        record_data = {
            "id": record_id,
            "event_id": getattr(entry, "event_id", None),
            "subscription_id": getattr(entry, "subscription_id", ""),
            "payment_id": getattr(entry, "payment_id", None),
            "decline_bucket": getattr(entry, "decline_bucket", ""),
            "reasoning": getattr(entry, "reasoning", ""),
            "decided_action": getattr(entry, "decided_action", ""),
            "attempt_number": getattr(entry, "attempt_number", 1),
            "retry_delay_seconds": getattr(entry, "retry_delay_seconds", None),
            "subscription_lifecycle_state": getattr(entry, "subscription_lifecycle_state", ""),
            "created_at": getattr(entry, "created_at", None) or now_iso
        }

    supabase = get_supabase_client()
    if supabase:
        try:
            response = supabase.table("recovery_audit_log").insert(record_data).execute()
            if response.data and len(response.data) > 0:
                logger.info(f"Recorded recovery audit log (ID: {record_id}) in Supabase.")
                return response.data[0]
        except Exception as e:
            logger.error(f"Error inserting recovery audit log into Supabase: {e}. Storing locally.")

    _local_audit_log_store.append(record_data)
    return record_data


def get_recovery_audit_logs(
    subscription_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Retrieves decision audit log entries, optionally filtered by subscription ID.
    """
    supabase = get_supabase_client()
    if supabase:
        try:
            query = supabase.table("recovery_audit_log").select("*").order("created_at", desc=True).limit(limit)
            if subscription_id:
                query = query.eq("subscription_id", subscription_id)
            response = query.execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching recovery audit logs from Supabase: {e}")

    results = _local_audit_log_store
    if subscription_id:
        results = [log for log in results if log.get("subscription_id") == subscription_id]
    return list(reversed(results[-limit:]))


def clear_local_store() -> None:
    """Helper for test cleanup."""
    global _local_webhook_store, _local_audit_log_store, _local_subscription_states
    _local_webhook_store.clear()
    _local_audit_log_store.clear()
    _local_subscription_states.clear()
