"""Security and contract tests for the first Agent Query API slice."""

from tests.conftest import SyncASGIClient


QUERY_PATH = "/agent-data/v1/query/customer_receivable_query"


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "api_version": "1.0.0",
        "select": ["customer_name", "region", "overdue_amount", "currency"],
        "filters": [{"field": "overdue_days", "op": "gte", "value": 30}],
        "order_by": [{"field": "overdue_amount", "direction": "desc"}],
        "limit": 20,
    }
    payload.update(overrides)
    return payload


def test_query_requires_authentication(client: SyncASGIClient) -> None:
    response = client.post(QUERY_PATH, json=_payload())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_policy_row_filter_restricts_agent_region(
    client: SyncASGIClient, agent_headers: dict[str, str]
) -> None:
    response = client.post(QUERY_PATH, headers=agent_headers, json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert [row["customer_name"] for row in body["data"]["rows"]] == [
        "华东示例客户A"
    ]
    assert all(row["region"] == "EAST" for row in body["data"]["rows"])
    assert body["policy"]["result_limit_applied"] == 20
    assert body["freshness"]["dataset_version"] == 12


def test_unpublished_field_is_rejected(
    client: SyncASGIClient, agent_headers: dict[str, str]
) -> None:
    response = client.post(
        QUERY_PATH,
        headers=agent_headers,
        json=_payload(select=["customer_name", "contact_phone"]),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FIELD_NOT_SELECTABLE"


def test_unapproved_filter_operator_is_rejected(
    client: SyncASGIClient, agent_headers: dict[str, str]
) -> None:
    response = client.post(
        QUERY_PATH,
        headers=agent_headers,
        json=_payload(filters=[{"field": "region", "op": "contains", "value": "E"}]),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILTER_NOT_ALLOWED"


def test_wrong_purpose_is_denied(
    client: SyncASGIClient, agent_headers: dict[str, str]
) -> None:
    headers = dict(agent_headers)
    headers["X-Purpose"] = "management_review"
    response = client.post(QUERY_PATH, headers=headers, json=_payload())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_unknown_tenant_cannot_discover_api(client: SyncASGIClient) -> None:
    headers = {
        "Authorization": "Bearer dev.tenant_999.AGENT.sales_risk_agent.EAST",
        "X-Purpose": "sales_risk_followup",
    }
    response = client.post(QUERY_PATH, headers=headers, json=_payload())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_VISIBLE"


def test_unknown_request_fields_are_rejected(
    client: SyncASGIClient, agent_headers: dict[str, str]
) -> None:
    response = client.post(
        QUERY_PATH,
        headers=agent_headers,
        json=_payload(sql="select * from secret_table"),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
