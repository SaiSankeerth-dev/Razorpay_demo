"""
Pytest configuration and global fixtures.
"""
import pytest
from db.config import settings
from db.repository import clear_local_store


@pytest.fixture(autouse=True, scope="session")
def configure_test_environment():
    """Sets local database mode for lightning fast test execution."""
    settings.USE_LOCAL_DB = True
    settings.ENVIRONMENT = "test"
    settings.RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret_for_suite_12345"


@pytest.fixture(autouse=True)
def clean_database_between_tests():
    """Clears in-memory database stores between test functions."""
    clear_local_store()
    yield
    clear_local_store()
