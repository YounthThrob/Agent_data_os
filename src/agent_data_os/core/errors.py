"""Stable application errors exposed through the public API contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    """Base exception carrying a stable, non-sensitive API error code."""

    code: str
    message: str
    status_code: int
    retryable: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)


class UnauthenticatedError(AppError):
    def __init__(self, message: str = "认证信息缺失或无效") -> None:
        super().__init__("UNAUTHENTICATED", message, 401, False)


class PolicyDeniedError(AppError):
    def __init__(self, reasons: list[str] | None = None) -> None:
        details = [{"reason": reason} for reason in (reasons or [])]
        super().__init__(
            "POLICY_DENIED", "当前身份无权执行该操作", 403, False, details
        )


class ResourceNotVisibleError(AppError):
    def __init__(self) -> None:
        # The same response is used for missing and invisible resources to prevent
        # callers from enumerating protected resources.
        super().__init__("RESOURCE_NOT_VISIBLE", "资源不存在或不可见", 404, False)


class InvalidArgumentError(AppError):
    def __init__(self, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__("INVALID_ARGUMENT", message, 400, False, details or [])


class FieldNotSelectableError(AppError):
    def __init__(self, fields: list[str]) -> None:
        super().__init__(
            "FIELD_NOT_SELECTABLE",
            "请求包含未发布的查询字段",
            400,
            False,
            [{"fields": fields}],
        )


class FilterNotAllowedError(AppError):
    def __init__(self, field_name: str, operator: str) -> None:
        super().__init__(
            "FILTER_NOT_ALLOWED",
            "字段或过滤操作符未授权",
            400,
            False,
            [{"field": field_name, "operator": operator}],
        )


class OrderNotAllowedError(AppError):
    def __init__(self, field_name: str) -> None:
        super().__init__(
            "ORDER_NOT_ALLOWED",
            "排序字段未授权",
            400,
            False,
            [{"field": field_name}],
        )


class AuditUnavailableError(AppError):
    """Fail closed when an auditable data operation cannot be recorded."""

    def __init__(self) -> None:
        super().__init__(
            "AUDIT_CHANNEL_UNAVAILABLE",
            "审计通道暂时不可用，请稍后重试",
            503,
            True,
        )
