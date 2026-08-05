"""Default-deny policy evaluation service."""

from __future__ import annotations

import uuid

from agent_data_os.domains.policy.models import (
    DecisionEffect,
    DecisionRequest,
    DecisionResult,
    Obligations,
)
from agent_data_os.domains.policy.ports import PolicyRepository


class PolicyEvaluator:
    """Evaluate explicit grants and produce immutable enforcement obligations."""

    def __init__(self, repository: PolicyRepository, policy_version: int = 1) -> None:
        self._repository = repository
        self._policy_version = policy_version

    def decide(self, request: DecisionRequest) -> DecisionResult:
        grants = self._repository.find_grants(request)
        matching = [g for g in grants if request.subject.purpose in g.purposes]
        if not matching:
            return DecisionResult(
                decision_id=f"pd_{uuid.uuid4().hex}",
                effect=DecisionEffect.DENY,
                policy_version=self._policy_version,
                reason_codes=("NO_MATCHING_GRANT",),
            )

        # Multiple matching grants are combined conservatively. The strictest
        # row limit wins and all immutable row restrictions are retained.
        limits = [grant.max_rows for grant in matching if grant.max_rows is not None]
        row_filters: list[tuple[str, str, object]] = []
        for grant in matching:
            if grant.region_from_subject:
                region = request.subject.attributes.get("region")
                if not region:
                    return DecisionResult(
                        decision_id=f"pd_{uuid.uuid4().hex}",
                        effect=DecisionEffect.DENY,
                        policy_version=self._policy_version,
                        reason_codes=("SUBJECT_REGION_MISSING",),
                    )
                row_filters.append(("region", "eq", region))

        obligations = Obligations(
            row_filters=tuple(row_filters),
            max_rows=min(limits) if limits else None,
            allow_export=False,
        )
        effect = (
            DecisionEffect.ALLOW_WITH_OBLIGATIONS
            if row_filters or limits
            else DecisionEffect.ALLOW
        )
        return DecisionResult(
            decision_id=f"pd_{uuid.uuid4().hex}",
            effect=effect,
            policy_version=self._policy_version,
            obligations=obligations,
            reason_codes=("EXPLICIT_GRANT",),
        )

