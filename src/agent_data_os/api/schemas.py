"""Pydantic transport schemas for the V1.0 API contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictRequest(BaseModel):
    """Reject unknown fields on security-sensitive public requests."""

    model_config = ConfigDict(extra="forbid")


class QueryFilterRequest(StrictRequest):
    field: str = Field(min_length=1, max_length=128)
    op: str = Field(min_length=1, max_length=32)
    value: Any


class OrderByRequest(StrictRequest):
    field: str = Field(min_length=1, max_length=128)
    direction: Literal["asc", "desc"] = "asc"


class QueryRequest(StrictRequest):
    api_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    select: list[str] = Field(min_length=1, max_length=50)
    filters: list[QueryFilterRequest] = Field(default_factory=list, max_length=20)
    order_by: list[OrderByRequest] = Field(default_factory=list, max_length=5)
    limit: int | None = Field(default=None, ge=1, le=1000)
    cursor: str | None = Field(default=None, max_length=2048)
    context: dict[str, Any] | None = None

    @field_validator("select")
    @classmethod
    def unique_selected_fields(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("select字段不能重复")
        return value


class PolicySubjectRequest(StrictRequest):
    tenant_id: str
    actor_type: Literal["USER", "AGENT", "SERVICE"]
    actor_id: str
    purpose: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class PolicyResourceRequest(StrictRequest):
    type: str
    id: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class PolicyDecisionRequest(StrictRequest):
    subject: PolicySubjectRequest
    resource: PolicyResourceRequest
    action: str
    environment: str = "PROD"


class DataSourceConnectionRequest(StrictRequest):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    tls_mode: Literal["DISABLE", "REQUIRE", "VERIFY_CA", "VERIFY_FULL"] = "VERIFY_FULL"
    network_zone: str = Field(min_length=1, max_length=64)


class DataSourceCredentialRequest(StrictRequest):
    secret_ref: str = Field(min_length=8, max_length=1024)


class CreateDataSourceRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["POSTGRESQL", "MYSQL", "ORACLE"]
    connector_version: str = Field(min_length=1, max_length=64)
    connection: DataSourceConnectionRequest
    credential: DataSourceCredentialRequest
    owner_id: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)


class SourceObjectRequest(StrictRequest):
    schema_name: str = Field(alias="schema", min_length=1, max_length=128)
    object_name: str = Field(alias="object", min_length=1, max_length=128)
    columns: list[str] = Field(min_length=1, max_length=500)
    primary_key: list[str] = Field(default_factory=list, max_length=20)


class SyncTargetRequest(StrictRequest):
    logical_dataset_name: str = Field(min_length=1, max_length=200)


class CreateSyncJobRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    data_source_id: str = Field(min_length=1, max_length=64)
    source_objects: list[SourceObjectRequest] = Field(min_length=1, max_length=100)
    sync_mode: Literal["FULL", "INCREMENTAL_TIMESTAMP", "CDC"]
    incremental: dict[str, Any] = Field(default_factory=dict)
    schedule: dict[str, Any] = Field(default_factory=dict)
    target: SyncTargetRequest


class CompleteIngestionRunRequest(StrictRequest):
    outcome: Literal["SUCCEEDED", "FAILED"] = "SUCCEEDED"
    result_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    error_code: str | None = Field(default=None, min_length=1, max_length=64)
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] = Field(default_factory=dict)
    schema_definition: list[dict[str, Any]] = Field(
        default_factory=list, alias="schema", max_length=1000
    )
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
