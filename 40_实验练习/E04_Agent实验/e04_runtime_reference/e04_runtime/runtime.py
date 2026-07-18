from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Mapping

from pydantic import ValidationError

from .audit import RedactedAuditLog
from .errors import (
    ApprovalExpired,
    ApprovalTargetMismatch,
    InvalidContract,
    InvalidTransition,
    InvalidToolOutput,
    RuntimeReferenceError,
)
from .models import (
    AppendMessageRequest,
    CreateSessionRequest,
    CreateTaskRequest,
    DecisionRequest,
    DraftOutput,
    Principal,
    PublishOutput,
    ResumeClaim,
    RetrieveOutput,
    ToolObservation,
    ToolProposal,
)
from .repository import AgentTask, Approval, InMemoryRepository, ResumeOutbox, SessionState
from .tools import ToolGateway, canonical_json, proposal_sha256, sha256_text


WORKFLOW_VERSION = "agent-report/v1"


class ManualClock:
    def __init__(self, initial: datetime | None = None) -> None:
        self._now = initial or datetime(2026, 7, 18, 0, 0, tzinfo=UTC)
        if self._now.tzinfo is None:
            raise ValueError("clock must be timezone-aware")
        self._lock = RLock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, **delta: float) -> datetime:
        with self._lock:
            self._now += timedelta(**delta)
            return self._now


class FixedPlanner:
    """Deterministic planner fixture. It never calls a model or network service."""

    def propose(self, task: AgentTask) -> Mapping[str, object]:
        if task.current_step == "retrieve_docs":
            return {
                "tool_name": "retrieve_docs",
                "arguments": {
                    "query": task.query,
                    "collection_id": task.collection_id,
                    "top_k": 2,
                },
            }
        if task.current_step == "draft_report":
            return {
                "tool_name": "draft_report",
                "arguments": {
                    "query": task.query,
                    "collection_id": task.collection_id,
                    "source_ids": list(task.retrieved_source_ids),
                },
            }
        raise InvalidContract(f"planner has no proposal for step {task.current_step}")


class AgentRuntime:
    def __init__(
        self,
        *,
        repository: InMemoryRepository,
        gateway: ToolGateway,
        clock: ManualClock,
        audit: RedactedAuditLog | None = None,
        planner: FixedPlanner | None = None,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.clock = clock
        self.audit = audit or RedactedAuditLog()
        self.planner = planner or FixedPlanner()
        self._executed_resume: dict[tuple[str, int], ToolObservation] = {}
        self._execution_lock = RLock()

    def create_task(self, principal: Principal, payload: Mapping[str, object]) -> AgentTask:
        request = self._validate(CreateTaskRequest, payload)
        now = self.clock.now()
        task = self.repository.create_task(
            principal=principal,
            query=request.query,
            collection_id=request.collection_id,
            workflow_version=WORKFLOW_VERSION,
            deadline_at=now + timedelta(seconds=request.deadline_seconds),
            now=now,
        )
        self._audit(principal, "task_created", {"task_id": task.task_id})
        return task

    def run_to_approval(
        self,
        principal: Principal,
        task_id: str,
        *,
        approval_ttl_seconds: int = 300,
    ) -> tuple[AgentTask, Approval]:
        if (
            isinstance(approval_ttl_seconds, bool)
            or not isinstance(approval_ttl_seconds, int)
            or not 1 <= approval_ttl_seconds <= 3600
        ):
            raise InvalidContract("approval_ttl_seconds must be an integer in [1, 3600]")
        task = self.repository.claim_initial(principal, task_id, now=self.clock.now())
        try:
            retrieve_proposal = self._proposal(self.planner.propose(task))
            retrieval = self.gateway.execute(
                principal=principal,
                proposal=retrieve_proposal,
                now=self.clock.now(),
                deadline_at=task.deadline_at,
            )
            retrieved = RetrieveOutput.model_validate_json(retrieval.payload_json)
            if not retrieved.source_ids:
                raise InvalidToolOutput("retrieval returned no authorized sources")
            task = self.repository.record_retrieval(
                principal,
                task_id,
                expected_version=task.version,
                source_ids=tuple(retrieved.source_ids),
                now=self.clock.now(),
            )
            self._audit(
                principal,
                "tool_completed",
                {
                    "task_id": task_id,
                    "tool_name": retrieval.tool_name,
                    "trust_label": retrieval.trust_label,
                    "source_count": len(retrieved.source_ids),
                },
            )

            draft_proposal = self._proposal(self.planner.propose(task))
            draft_observation = self.gateway.execute(
                principal=principal,
                proposal=draft_proposal,
                now=self.clock.now(),
                deadline_at=task.deadline_at,
            )
            draft = DraftOutput.model_validate_json(draft_observation.payload_json)
            publish_proposal = ToolProposal.model_validate(
                {
                    "tool_name": "publish_report",
                    "arguments": {
                        "report_id": f"report/{task.task_id}",
                        "draft_sha256": sha256_text(draft.draft),
                    },
                }
            )
            now = self.clock.now()
            expires_at = min(
                task.deadline_at,
                now + timedelta(seconds=approval_ttl_seconds),
            )
            waiting, approval = self.repository.create_waiting_approval(
                principal,
                task_id,
                expected_version=task.version,
                draft=draft.draft,
                action_json=canonical_json(publish_proposal.model_dump(mode="json")),
                action_sha256=proposal_sha256(publish_proposal),
                expires_at=expires_at,
                now=now,
            )
            self._audit(
                principal,
                "approval_requested",
                {
                    "task_id": task_id,
                    "approval_id": approval.approval_id,
                    "draft_sha256": approval.draft_sha256,
                    "action_sha256": approval.action_sha256,
                },
            )
            return waiting, approval
        except RuntimeReferenceError as exc:
            current = self.repository.get_task(principal, task_id)
            if current.status not in {"failed", "succeeded"}:
                self.repository.fail_task(
                    principal,
                    task_id,
                    expected_version=current.version,
                    error_type=exc.code,
                    now=self.clock.now(),
                )
            self._audit(
                principal,
                "task_failed",
                {"task_id": task_id, "error_type": exc.code},
            )
            raise

    def decide_approval(
        self,
        principal: Principal,
        *,
        task_id: str,
        approval_id: str,
        payload: Mapping[str, object],
    ) -> tuple[AgentTask, Approval, ResumeOutbox | None]:
        request = self._validate(DecisionRequest, payload)
        try:
            result = self.repository.decide_approval(
                principal,
                task_id=task_id,
                approval_id=approval_id,
                request=request,
                now=self.clock.now(),
            )
        except ApprovalExpired:
            self._audit(
                principal,
                "approval_timeout",
                {"task_id": task_id, "approval_id": approval_id},
            )
            raise
        self._audit(
            principal,
            f"approval_{request.decision}",
            {
                "task_id": task_id,
                "approval_id": approval_id,
                "approval_note_present": request.comment is not None,
                "approval_note_length": len(request.comment or ""),
            },
        )
        return result

    def expire_approvals(self) -> tuple[AgentTask, ...]:
        expired = self.repository.expire_pending_approvals(now=self.clock.now())
        for task in expired:
            principal = Principal(
                tenant_id=task.tenant_id,
                owner_user_id=task.owner_user_id,
                capabilities=frozenset(),
                grants=(),
            )
            self._audit(
                principal,
                "approval_timeout",
                {"task_id": task.task_id, "approval_id": task.approval_id or ""},
            )
        return expired

    def claim_resume(self, *, worker_id: str, lease_seconds: int = 30) -> ResumeClaim | None:
        if not worker_id or len(worker_id) > 64:
            raise InvalidContract("worker_id must contain 1 to 64 characters")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 300
        ):
            raise InvalidContract("lease_seconds must be an integer in [1, 300]")
        return self.repository.claim_resume(
            worker_id=worker_id,
            now=self.clock.now(),
            lease_seconds=lease_seconds,
        )

    def execute_resume(self, principal: Principal, claim: ResumeClaim) -> ToolObservation:
        task, outbox = self.repository.validate_resume_claim(
            principal,
            claim,
            now=self.clock.now(),
        )
        if (
            task.action_json is None
            or task.action_sha256 is None
            or task.draft_sha256 is None
            or sha256_text(task.action_json) != task.action_sha256
            or outbox.action_sha256 != task.action_sha256
            or sha256_text(task.draft or "") != task.draft_sha256
        ):
            raise ApprovalTargetMismatch()
        try:
            proposal = ToolProposal.model_validate_json(task.action_json)
        except ValidationError as exc:
            raise InvalidContract("stored action no longer matches proposal schema") from exc

        observation = self.gateway.execute(
            principal=principal,
            proposal=proposal,
            now=self.clock.now(),
            deadline_at=task.deadline_at,
            idempotency_key=claim.approval_id,
        )
        PublishOutput.model_validate_json(observation.payload_json)
        with self._execution_lock:
            self._executed_resume[(claim.approval_id, claim.claim_version)] = observation
        self._audit(
            principal,
            "side_effect_executed",
            {
                "task_id": task.task_id,
                "approval_id": claim.approval_id,
                "tool_name": proposal.tool_name,
            },
        )
        return observation

    def finalize_resume(self, principal: Principal, claim: ResumeClaim) -> AgentTask:
        with self._execution_lock:
            observation = self._executed_resume.get(
                (claim.approval_id, claim.claim_version)
            )
        if observation is None:
            raise InvalidTransition("side effect has not been executed")
        output = PublishOutput.model_validate_json(observation.payload_json)
        task = self.repository.finalize_resume(
            principal,
            claim,
            delivery_id=output.delivery_id,
            now=self.clock.now(),
        )
        with self._execution_lock:
            self._executed_resume.pop((claim.approval_id, claim.claim_version), None)
        self._audit(
            principal,
            "task_succeeded",
            {"task_id": task.task_id, "delivery_id": output.delivery_id},
        )
        return task

    def create_session(
        self,
        principal: Principal,
        payload: Mapping[str, object],
    ) -> SessionState:
        request = self._validate(CreateSessionRequest, payload)
        state = self.repository.create_session(principal, session_id=request.session_id)
        self._audit(principal, "session_created", {"session_id": state.session_id})
        return state

    def append_session_message(
        self,
        principal: Principal,
        *,
        session_id: str,
        payload: Mapping[str, object],
    ) -> SessionState:
        request = self._validate(AppendMessageRequest, payload)
        state = self.repository.append_session_message(
            principal,
            session_id=session_id,
            expected_version=request.expected_version,
            text=request.text,
        )
        self._audit(
            principal,
            "session_message_appended",
            {"session_id": session_id, "message": request.text, "version": state.version},
        )
        return state

    def _audit(self, principal: Principal, event_type: str, details: Mapping[str, object]) -> None:
        self.audit.append(
            occurred_at=self.clock.now(),
            event_type=event_type,
            principal=principal,
            details=details,
        )

    @staticmethod
    def _validate(model: type[CreateTaskRequest] | type[CreateSessionRequest] | type[AppendMessageRequest] | type[DecisionRequest], payload: Mapping[str, object]):  # type: ignore[no-untyped-def]
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise InvalidContract("request failed strict schema validation") from exc

    @staticmethod
    def _proposal(payload: Mapping[str, object]) -> ToolProposal:
        try:
            return ToolProposal.model_validate(payload)
        except ValidationError as exc:
            raise InvalidContract("planner proposal failed strict schema validation") from exc
