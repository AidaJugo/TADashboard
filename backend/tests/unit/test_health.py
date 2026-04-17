from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.unit
def test_readyz_returns_ok(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.unit
def test_request_id_header_is_echoed(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "test-req-id"})

    assert response.headers["X-Request-ID"] == "test-req-id"
