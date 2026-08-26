"""
Supabase client initializer and connection manager.
"""
import logging
from typing import Optional
from supabase import create_client, Client
from db.config import settings

logger = logging.getLogger(__name__)

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """
    Initializes and returns the Supabase client instance.
    Returns None if credentials are placeholder/unconfigured.
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY

    # Check if URL and Key are real / configured
    if not url or "placeholder" in url or not key or "placeholder" in key:
        logger.warning(
            "Supabase credentials not configured in .env. Operating in local in-memory fallback mode."
        )
        return None

    try:
        _supabase_client = create_client(url, key)
        logger.info("Supabase client successfully initialized.")
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None
