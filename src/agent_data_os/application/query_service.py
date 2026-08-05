"""Query API application service implementing the first vertical slice."""

from __future__ import annotations

from agent_data_os.core.context import RequestContext
from agent_data_os.core.errors import (
    FieldNotSelectableError,
    FilterNotAllowedError,
    InvalidArgumentError,
    OrderNotAllowedError,
    PolicyDeniedError,
    ResourceNotVisibleError,
)
from agent_data_os.domains.data_service.models import (
    QueryCommand,
    QueryFilter,
    QueryResult,
    SUPPORTED_OPERATORS,
)
from agent_data_os.domains.data_service.ports import QueryApiRepository, QueryDataPort
from agent_data_os.domains.policy.models import DecisionEffect, DecisionRequest, Resource
from agent_data_os.domains.policy.ports import PolicyDecisionPort


class QueryApplicationService:
    """Validate a published query contract, authorize it, and execute logical data access."""

    def __init__(
        self,
        api_repository: QueryApiRepository,
        data_port: QueryDataPort,
        policy_port: PolicyDecisionPort,
    ) -> None:
        self._api_repository = api_repository
        self._data_port = data_port
        self._policy_port = policy_port

    def execute(self, context: RequestContext, command: QueryCommand) -> QueryResult:
        definition = self._api_repository.get_published(
            context.security.tenant_id, command.api_code
        )
        if definition is None:
            raise ResourceNotVisibleError()
        if command.api_version != definition.version:
            raise InvalidArgumentError("请求的Data API版本不可用")
        if context.security.purpose not in definition.allowed_purposes:
            raise PolicyDeniedError(["PURPOSE_NOT_ALLOWED"])

        unknown_fields = sorted(
            set(command.selected_fields) - definition.selectable_fields
        )
        if unknown_fields:
            raise FieldNotSelectableError(unknown_fields)

        for query_filter in command.filters:
            if query_filter.operator not in SUPPORTED_OPERATORS:
                raise FilterNotAllowedError(query_filter.field, query_filter.operator)
            allowed = definition.allowed_filters.get(query_filter.field, frozenset())
            if query_filter.operator not in allowed:
                raise FilterNotAllowedError(query_filter.field, query_filter.operator)

        for order in command.order_by:
            if order.field not in definition.allowed_order_fields:
                raise OrderNotAllowedError(order.field)
            if order.direction not in {"asc", "desc"}:
                raise InvalidArgumentError("排序方向只能为asc或desc")

        decision = self._policy_port.decide(
            DecisionRequest(
                subject=context.security,
                resource=Resource(
                    resource_type="DATA_API_VERSION",
                    resource_id=f"{definition.code}:{definition.version}",
                    attributes={"dataset_id": definition.dataset_id},
                ),
                action="INVOKE",
                environment=context.environment,
            )
        )
        if decision.effect is DecisionEffect.DENY:
            raise PolicyDeniedError(list(decision.reason_codes))

        requested_limit = command.limit or definition.default_limit
        if requested_limit < 1:
            raise InvalidArgumentError("limit必须大于0")
        effective_limit = min(requested_limit, definition.maximum_limit)
        if decision.obligations.max_rows is not None:
            effective_limit = min(effective_limit, decision.obligations.max_rows)

        # Policy row filters are appended after caller validation and marked
        # immutable. The caller cannot remove or override these conditions.
        policy_filters = tuple(
            QueryFilter(field, operator, value, immutable=True)
            for field, operator, value in decision.obligations.row_filters
        )
        rows = self._data_port.query(
            tenant_id=context.security.tenant_id,
            dataset_id=definition.dataset_id,
            selected_fields=command.selected_fields,
            filters=command.filters + policy_filters,
            order_by=command.order_by,
            # Fetch one extra row to determine truncation without disclosing a total.
            limit=effective_limit + 1,
        )
        truncated = len(rows) > effective_limit
        rows = rows[:effective_limit]
        schema = tuple(
            {
                "name": field,
                "type": definition.field_types.get(field, "string"),
                "masked": False,
            }
            for field in command.selected_fields
        )
        return QueryResult(
            rows=tuple(rows),
            schema=schema,
            dataset_version=definition.dataset_version,
            freshness_at=definition.freshness_at,
            quality_score=definition.quality_score,
            decision_id=decision.decision_id,
            policy_version=decision.policy_version,
            result_limit_applied=effective_limit,
            truncated=truncated,
        )

