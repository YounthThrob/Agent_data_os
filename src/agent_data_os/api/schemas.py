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

