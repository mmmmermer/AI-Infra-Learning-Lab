from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CreateTaskRequest(StrictModel):
    query: StrictStr = Field(min_length=1, max_length=500)
    collection_id: StrictStr = Field(min_length=1, max_length=100)
    deadline_seconds: StrictInt = Field(ge=1, le=3600)


class CreateSessionRequest(StrictModel):
    session_id: StrictStr = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class AppendMessageRequest(StrictModel):
    text: StrictStr = Field(min_length=1, max_length=2000)
    expected_version: StrictInt = Field(ge=0)


class ToolProposal(StrictModel):
    tool_name: StrictStr = Field(min_length=1, max_length=64)
    arguments: dict[str, object]


class RetrieveArgs(StrictModel):
    query: StrictStr = Field(min_length=1, max_length=500)
    collection_id: StrictStr = Field(min_length=1, max_length=100)
    top_k: StrictInt = Field(ge=1, le=10)


class RetrieveOutput(StrictModel):
    chunks: list[StrictStr]
    source_ids: list[StrictStr]


class DraftArgs(StrictModel):
    query: StrictStr = Field(min_length=1, max_length=500)
    collection_id: StrictStr = Field(min_length=1, max_length=100)
    source_ids: list[StrictStr] = Field(min_length=1, max_length=10)


class DraftOutput(StrictModel):
    draft: StrictStr = Field(min_length=1, max_length=5000)
    source_ids: list[StrictStr] = Field(min_length=1, max_length=10)


class PublishArgs(StrictModel):
    report_id: StrictStr = Field(pattern=r"^report/[a-zA-Z0-9_-]+$")
    draft_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class PublishOutput(StrictModel):
    report_id: StrictStr
    delivery_id: StrictStr


class DecisionRequest(StrictModel):
    decision: Literal["approved", "rejected"]
    expected_version: StrictInt = Field(ge=0)
    comment: StrictStr | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def require_rejection_comment(self) -> DecisionRequest:
        if self.decision == "rejected" and self.comment is None:
            raise ValueError("rejected decisions require a comment")
        return self


@dataclass(frozen=True, slots=True)
class ResourceGrant:
    action: str
    resource_pattern: str
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    tenant_id: str
    owner_user_id: str
    capabilities: tuple[str, ...]
    grants: tuple[ResourceGrant, ...]


@dataclass(frozen=True, slots=True)
class Principal:
    tenant_id: str
    owner_user_id: str
    capabilities: frozenset[str]
    grants: tuple[ResourceGrant, ...]

    @classmethod
    def from_verified_claims(cls, claims: VerifiedClaims) -> Principal:
        return cls(
            tenant_id=claims.tenant_id,
            owner_user_id=claims.owner_user_id,
            capabilities=frozenset(claims.capabilities),
            grants=claims.grants,
        )


@dataclass(frozen=True, slots=True)
class Authorization:
    action: str
    resource: str
    authorized_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolObservation:
    tool_name: str
    trust_label: Literal["untrusted_tool_output"]
    payload_json: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    authorization: Authorization
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class ResumeClaim:
    outbox_id: str
    task_id: str
    approval_id: str
    worker_id: str
    claim_version: int
    task_version: int
    lease_until: datetime
