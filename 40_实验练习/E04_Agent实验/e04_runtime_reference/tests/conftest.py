from __future__ import annotations

from dataclasses import dataclass

import pytest

from e04_runtime import (
    AgentRuntime,
    InMemoryRepository,
    ManualClock,
    Principal,
    RedactedAuditLog,
    ResourceGrant,
    VerifiedClaims,
    build_default_gateway,
)
from e04_runtime.tools import DeterministicRetriever, IdempotentPublisher


@dataclass(frozen=True)
class Harness:
    runtime: AgentRuntime
    repository: InMemoryRepository
    clock: ManualClock
    audit: RedactedAuditLog
    retriever: DeterministicRetriever
    publisher: IdempotentPublisher


def make_principal(
    *,
    tenant_id: str = "tenant-a",
    owner_user_id: str = "owner-a",
    capabilities: tuple[str, ...] = (
        "rag:query",
        "report:draft",
        "report:publish",
        "approval:decide",
    ),
) -> Principal:
    return Principal.from_verified_claims(
        VerifiedClaims(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            capabilities=capabilities,
            grants=(
                ResourceGrant(
                    "rag:query",
                    "infra",
                    ("src-public", "src-owner"),
                ),
                ResourceGrant(
                    "report:draft",
                    "infra",
                    ("src-public", "src-owner"),
                ),
                ResourceGrant("report:publish", "report/*"),
            ),
        )
    )


@pytest.fixture
def principal() -> Principal:
    return make_principal()


@pytest.fixture
def other_principal() -> Principal:
    return make_principal(tenant_id="tenant-b", owner_user_id="owner-b")


@pytest.fixture
def harness() -> Harness:
    repository = InMemoryRepository()
    gateway, retriever, publisher = build_default_gateway()
    clock = ManualClock()
    audit = RedactedAuditLog()
    runtime = AgentRuntime(
        repository=repository,
        gateway=gateway,
        clock=clock,
        audit=audit,
    )
    return Harness(runtime, repository, clock, audit, retriever, publisher)
