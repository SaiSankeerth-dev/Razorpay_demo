"""
Unit tests for Razorpay webhook signature verification using the official SDK.
"""
import pytest
import hmac
import hashlib
import razorpay.errors
from webhooks.verifier import verify_razorpay_signature


def compute_test_signature(body: str, secret: str) -> str:
    """Helper to compute valid HMAC-SHA256 signature."""
    return hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def test_valid_signature_verification():
    """Verify that authentic signature is accepted by the SDK utility."""
    secret = "rzp_secret_test_key_123"
    body = '{"event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_123"}}}}'
    sig = compute_test_signature(body, secret)

    result = verify_razorpay_signature(body=body, signature=sig, secret=secret)
    assert result is True


def test_valid_signature_with_bytes_body():
    """Verify that bytes payload is handled correctly."""
    secret = "rzp_secret_test_key_123"
    body_str = '{"event":"subscription.pending"}'
    body_bytes = body_str.encode("utf-8")
    sig = compute_test_signature(body_str, secret)

    result = verify_razorpay_signature(body=body_bytes, signature=sig, secret=secret)
    assert result is True


def test_tampered_signature_rejection():
    """Verify that altered signature is strictly rejected by the SDK."""
    secret = "rzp_secret_test_key_123"
    body = '{"event":"payment.failed"}'
    invalid_sig = "a" * 64

    with pytest.raises(razorpay.errors.SignatureVerificationError):
        verify_razorpay_signature(body=body, signature=invalid_sig, secret=secret)


def test_tampered_body_rejection():
    """Verify that altering the body invalidates the signature."""
    secret = "rzp_secret_test_key_123"
    original_body = '{"event":"payment.failed","amount":1000}'
    tampered_body = '{"event":"payment.failed","amount":5000}'
    sig = compute_test_signature(original_body, secret)

    with pytest.raises(razorpay.errors.SignatureVerificationError):
        verify_razorpay_signature(body=tampered_body, signature=sig, secret=secret)


def test_wrong_secret_rejection():
    """Verify that signature signed with a different secret is rejected."""
    correct_secret = "correct_secret_key"
    wrong_secret = "wrong_secret_key"
    body = '{"event":"subscription.halted"}'
    sig = compute_test_signature(body, wrong_secret)

    with pytest.raises(razorpay.errors.SignatureVerificationError):
        verify_razorpay_signature(body=body, signature=sig, secret=correct_secret)


def test_missing_signature_rejection():
    """Verify that empty/None signature raises error."""
    secret = "secret"
    body = '{"event":"payment.failed"}'

    with pytest.raises(razorpay.errors.SignatureVerificationError):
        verify_razorpay_signature(body=body, signature="", secret=secret)
