import pytest
from fastapi.testclient import TestClient
from app import app

@pytest.fixture
def client():
    """Shared FastAPI TestClient fixture across all test suites."""
    return TestClient(app, raise_server_exceptions=False)

