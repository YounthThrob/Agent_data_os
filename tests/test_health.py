"""Health endpoints remain available without business authentication."""

from tests.conftest import SyncASGIClient


def test_liveness(client: SyncASGIClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
    assert response.headers["X-Request-Id"].startswith("req_")


def test_readiness(client: SyncASGIClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["environment"] == "test"
