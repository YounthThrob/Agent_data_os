"""Dataset and immutable version values created by ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Dataset:
    id: str
    tenant_id: str
    logical_name: str
    status: str
    active_version_id: str | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    id: str
    tenant_id: str
    dataset_id: str
    version_number: int
    schema: tuple[dict[str, Any], ...]
    manifest: dict[str, Any]
    checkpoint: dict[str, Any]
    row_count: int
    content_hash: str
    status: str
    created_at: datetime
