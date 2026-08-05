"""Ports owned by the policy domain."""

from __future__ import annotations

from typing import Protocol

from agent_data_os.domains.policy.models import DecisionRequest, DecisionResult, Grant


class PolicyRepository(Protocol):
    def find_grants(self, request: DecisionRequest) -> list[Grant]:
        ...


class PolicyDecisionPort(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResult:
        ...

