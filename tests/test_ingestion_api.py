"""Public ingestion contract and authorization tests."""

from __future__ import annotations

import hashlib
import json

from tests.conftest import SyncASGIClient


USER_HEADERS = {
    "Authorization": "Bearer dev.tenant_001.USER.data_admin.EAST",
    "X-Purpose": "data_ingestion",
}
SERVICE_HEADERS = {
    "Authorization": "Bearer dev.tenant_001.SERVICE.ingestion_worker.EAST",
    "X-Purpose": "data_ingestion_callback",
}


def _source_payload() -> dict[str, object]:
    return {
        "name": "CRM read only",
        "source_type": "POSTGRESQL",
        "connector_version": "postgresql-1.0",
        "connection": {
            "host": "crm-db.internal",
            "port": 5432,
            "database": "crm",
            "tls_mode": "VERIFY_FULL",
            "network_zone": "enterprise-data-zone",
        },
        "credential": {"secret_ref": "vault://ados/tenant001/crm-ro"},
        "owner_id": "data_admin",
    }


def _create_tested_source(client: SyncASGIClient) -> str:
    created = client.post(
        "/api/v1/data-sources", headers=USER_HEADERS, json=_source_payload()
    )
    assert created.status_code == 201
    assert "secret_ref" not in created.text
    source_id = created.json()["data"]["id"]
    tested = client.post(
        f"/api/v1/data-sources/{source_id}/test", headers=USER_HEADERS
    )
    assert tested.status_code == 200
    assert tested.json()["data"]["status"] == "TESTED"
    return source_id


def test_data_source_discovery_hides_secret(client: SyncASGIClient) -> None:
    source_id = _create_tested_source(client)
    response = client.post(
        f"/api/v1/data-sources/{source_id}/discover", headers=USER_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["schema_objects"] == []
    assert "vault://" not in response.text


def test_agent_cannot_manage_data_sources(
    client: SyncASGIClient, agent_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/data-sources", headers=agent_headers, json=_source_payload()
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_connection_rejects_inline_credentials(client: SyncASGIClient) -> None:
    payload = _source_payload()
    payload["connection"]["password"] = "must-not-be-accepted"
    response = client.post(
        "/api/v1/data-sources", headers=USER_HEADERS, json=payload
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_sync_run_is_idempotent_and_worker_completes_it(
    client: SyncASGIClient,
) -> None:
    source_id = _create_tested_source(client)
    job_response = client.post(
        "/api/v1/sync-jobs",
        headers=USER_HEADERS,
        json={
            "name": "CRM customers daily",
            "data_source_id": source_id,
            "source_objects": [
                {
                    "schema": "public",
                    "object": "customers",
                    "columns": ["id", "name", "region"],
                    "primary_key": ["id"],
                }
            ],
            "sync_mode": "FULL",
            "schedule": {"type": "MANUAL"},
            "target": {"logical_dataset_name": "crm.customers"},
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["data"]["id"]

    run_headers = {**USER_HEADERS, "Idempotency-Key": "schedule-20260805"}
    first = client.post(f"/api/v1/sync-jobs/{job_id}/runs", headers=run_headers)
    second = client.post(f"/api/v1/sync-jobs/{job_id}/runs", headers=run_headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    run_id = first.json()["data"]["id"]

    rows = [{"id": 1, "name": "Acme", "region": "EAST"}]
    result_hash = hashlib.sha256(
        json.dumps(rows, sort_keys=True).encode("utf-8")
    ).hexdigest()
    completed = client.post(
        f"/internal/v1/ingestion/runs/{run_id}/callbacks",
        headers=SERVICE_HEADERS,
        json={
            "result_hash": result_hash,
            "checkpoint": {"offset": 1},
            "manifest": {
                "row_count": 1,
                "content_hash": result_hash,
                "quality_status": "PASS",
            },
            "schema": [{"name": "id", "type": "integer"}],
            "rows": rows,
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "SUCCEEDED"
    assert completed.json()["data"]["dataset_version_id"].startswith(
        "dataset_version_"
    )


def test_worker_cannot_complete_another_tenants_run(client: SyncASGIClient) -> None:
    headers = {
        "Authorization": "Bearer dev.tenant_999.SERVICE.ingestion_worker.EAST",
        "X-Purpose": "data_ingestion_callback",
    }
    response = client.post(
        "/internal/v1/ingestion/runs/run_hidden/callbacks",
        headers=headers,
        json={
            "result_hash": "a" * 64,
            "checkpoint": {},
            "manifest": {
                "row_count": 0,
                "content_hash": "a" * 64,
                "quality_status": "PASS",
            },
            "schema": [],
            "rows": [],
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_VISIBLE"
