"""
Webhook signature verification module using the official razorpay-python SDK.
"""
import logging
import razorpay
from razorpay.errors import SignatureVerificationError

logger = logging.getLogger(__name__)

# Reusable SDK client utility
_utility = razorpay.utility.Utility()


def verify_razorpay_signature(body: bytes | str, signature: str, secret: str) -> bool:
    """
    Verifies Razorpay webhook signature using the official SDK's Utility class.

    Args:
        body: The exact raw request body (bytes or string).
        signature: The signature provided in the 'X-Razorpay-Signature' header.
        secret: The webhook secret configured in Razorpay dashboard.

    Returns:
        True if the signature is authentic and verified.

    Raises:
        SignatureVerificationError: If verification fails or signature is tampered.
    """
    if not signature:
        logger.warning("Webhook verification failed: Missing X-Razorpay-Signature header.")
        raise SignatureVerificationError("Missing X-Razorpay-Signature header.")

    if not secret or secret == "placeholder_webhook_secret":
        logger.warning(
            "Webhook verification caution: RAZORPAY_WEBHOOK_SECRET is not configured or using default."
        )

    # Convert bytes to string if needed
    if isinstance(body, bytes):
        body_str = body.decode("utf-8")
    else:
        body_str = body

    try:
        # Use official razorpay-python SDK verification method
        # Under the hood, this computes hmac-sha256(key=secret, msg=body) and performs hmac.compare_digest
        _utility.verify_webhook_signature(body_str, signature, secret)
        return True
    except SignatureVerificationError as e:
        logger.warning(f"Razorpay Signature Verification Failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during signature verification: {e}")
        raise SignatureVerificationError(f"Signature verification error: {str(e)}")
