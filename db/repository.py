"""
Database Repository for storing and retrieving raw Webhook events.
Handles Supabase table writes with fallback to local store when testing offline.
"""
import uuid
import datetime
import logging
from typing import Optional, Dict, Any, List
from db.client import get_supabase_client

logger = logging.getLogger(__name__)

# Local in-memory store for unit tests / fallback when offline
_local_webhook_store: List[Dict[str, Any]] = []


def save_raw_webhook(
    event_type: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, Any]] = None,
    signature_valid: bool = True,
    event_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Persists a raw, unprocessed webhook event to the database.

    Args:
        event_type: The Razorpay event name (e.g. 'subscription.pending', 'payment.failed')
        payload: Full raw JSON payload dictionary
        headers: Request headers dictionary (for signature auditing)
        signature_valid: Boolean indicating whether HMAC-SHA256 signature verification passed
        event_id: Optional event ID (e.g. from X-Razorpay-Event-Id header or payload)

    Returns:
        The inserted record dictionary.
    """
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
                logger.info(f"Successfully recorded webhook event {event_type} (ID: {record_id}) in Supabase.")
                return response.data[0]
            logger.info(f"Recorded webhook event {event_type} in Supabase.")
            return record_data
        except Exception as e:
            logger.error(f"Error inserting webhook into Supabase: {e}. Storing in local audit store.")
            _local_webhook_store.append(record_data)
            return record_data
    else:
        logger.info(f"Supabase client not active. Recorded webhook event {event_type} in local audit store.")
        _local_webhook_store.append(record_data)
        return record_data


def get_webhook_events(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves recent raw webhook events.
    """
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
    """
    Retrieves the most recent webhook event matching a specific event type.
    """
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


def clear_local_store() -> None:
    """Helper for test cleanup."""
    global _local_webhook_store
    _local_webhook_store.clear()
