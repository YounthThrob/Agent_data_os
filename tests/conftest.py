"""Shared test application configured with explicit development authentication.

The installed Starlette version predates httpx 0.28's TestClient changes. This
small synchronous facade uses httpx's supported ASGI transport directly.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from agent_data_os.core.config import Settings
from agent_data_os.main import create_app


class SyncASGIClient:
    """Minimal synchronous client backed by httpx's ASGI transport."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: object) -> httpx.Response:
        return self.request("POST", path, **kwargs)


@pytest.fixture()
def client() -> SyncASGIClient:
    settings = Settings(
        environment="test",
        allow_insecure_dev_auth=True,
        default_query_limit=20,
        max_query_limit=100,
    )
    return SyncASGIClient(create_app(settings))


@pytest.fixture()
def agent_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev.tenant_001.AGENT.sales_risk_agent.EAST",
        "X-Purpose": "sales_risk_followup",
    }
