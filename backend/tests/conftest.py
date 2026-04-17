"""Shared pytest fixtures.

TODO: add fixtures for
- in-memory/dockerised Postgres per test session
- FastAPI TestClient with a seeded allowlisted user
- parameterised role fixtures (admin/editor/viewer) for authz tests
- synthetic Sheet data (never real employee names)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
