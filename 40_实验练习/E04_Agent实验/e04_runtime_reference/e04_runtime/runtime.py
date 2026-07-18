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
    TaskCancelled,
    VersionConflict,
)
from .models import (
    AppendMessageRequest,
    CancelTaskRequest,
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
MAX_AUTONOMOUS_STEPS = 2


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

    def cancel_task(
        self,
        principal: Principal,
        *,
        task_id: str,
        payload: Mapping[str, object],
    ) -> AgentTask:
        request = self._validate(CancelTaskRequest, payload)
        try:
            task = self.repository.cancel_task(
                principal,
                task_id,
                expected_version=request.expected_version,
                reason_present=request.reason is not None,
                reason_length=len(request.reason or ""),
                now=self.clock.now(),
            )
        except InvalidTransition:
            self._audit(
                principal,
                "task_cancel_rejected",
                {"task_id": task_id, "error_type": "invalid_transition"},
            )
            raise
        self._audit(
            principal,
            "task_cancelled",
            {
                "task_id": task_id,
                "current_step": task.current_step or "none",
                "reason_present": request.reason is not None,
                "reason_length": len(request.reason or ""),
            },
        )
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
            raise InvalidContract(
                "approval_ttl_seconds must be an integer in [1, 3600]"
            )
        task = self.repository.get_task(principal, task_id)
        if task.status == "waiting_approval" and task.current_step == "human_approval":
            if task.approval_id is None:
                raise InvalidTransition("waiting task has no approval")
            approval = self.repository.get_approval(
                principal,
                task_id,
                task.approval_id,
            )
            if approval.status != "pending":
                raise InvalidTransition("waiting task has no pending approval")
            return task, approval

        try:
            task = self.repository.claim_initial(
                principal,
                task_id,
                expected_version=task.version,
                now=self.clock.now(),
            )
        except TaskCancelled:
            self._audit(
                principal,
                "task_cancellation_observed",
                {"task_id": task_id, "current_step": task.current_step or "none"},
            )
            raise
        except (VersionConflict, InvalidTransition):
            raise

        try:
            for step_number in range(1, MAX_AUTONOMOUS_STEPS + 1):
                task = self.repository.assert_active(
                    principal,
                    task_id,
                    expected_version=task.version,
                )
                proposal = self._proposal(self.planner.propose(task))
                self.repository.assert_active(
                    principal,
                    task_id,
                    expected_version=task.version,
                )
                observation = self.gateway.execute(
                    principal=principal,
                    proposal=proposal,
                    now=self.clock.now(),
                    deadline_at=task.deadline_at,
                )
                self.repository.assert_active(
                    principal,
                    task_id,
                    expected_version=task.version,
                )

                if task.current_step == "retrieve_docs":
                    retrieved = RetrieveOutput.model_validate_json(observation.payload_json)
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
                            "tool_name": observation.tool_name,
                            "trust_label": observation.trust_label,
                            "source_count": len(retrieved.source_ids),
                            "step_number": step_number,
                        },
                    )
                    continue

                if task.current_step != "draft_report":
                    raise InvalidTransition("runtime reached an unsupported step")
                draft = DraftOutput.model_validate_json(observation.payload_json)
                if tuple(draft.source_ids) != task.retrieved_source_ids:
                    raise InvalidToolOutput("draft evidence no longer matches retrieval")
                self._audit(
                    principal,
                    "tool_completed",
                    {
                        "task_id": task_id,
                        "tool_name": observation.tool_name,
                        "trust_label": observation.trust_label,
                        "source_count": len(draft.source_ids),
                        "step_number": step_number,
                    },
                )
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
            raise InvalidTransition("autonomous step limit reached")
        except TaskCancelled:
            self._audit(
                principal,
                "task_cancellation_observed",
                {"task_id": task_id, "current_step": task.current_step or "none"},
            )
            raise
        except RuntimeReferenceError as exc:
            self._record_task_failure(principal, task_id, exc.code)
            raise
        except Exception as exc:
            normalized = InvalidToolOutput("unexpected runtime step failure")
            self._record_task_failure(principal, task_id, normalized.code)
            raise normalized from exc

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

    def claim_resume(
        self,
        *,
        worker_id: str,
        tenant_scope: frozenset[str],
        lease_seconds: int = 30,
    ) -> ResumeClaim | None:
        if (
            not isinstance(worker_id, str)
            or not worker_id
            or len(worker_id) > 64
            or any(
                ord(character) <= 32 or ord(character) == 127
                for character in worker_id
            )
        ):
            raise InvalidContract("worker_id must contain 1 to 64 characters")
        if (
            not isinstance(tenant_scope, frozenset)
            or not tenant_scope
            or any(
                not isinstance(tenant_id, str)
                or not tenant_id
                or len(tenant_id) > 100
                or any(
                    ord(character) <= 32 or ord(character) == 127
                    for character in tenant_id
                )
                for tenant_id in tenant_scope
            )
        ):
            raise InvalidContract(
                "tenant_scope must be a non-empty trusted frozenset"
            )
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 300
        ):
            raise InvalidContract("lease_seconds must be an integer in [1, 300]")
        return self.repository.claim_resume(
            worker_id=worker_id,
            tenant_scope=tenant_scope,
            now=self.clock.now(),
            lease_seconds=lease_seconds,
        )

    def execute_resume(self, principal: Principal, claim: ResumeClaim) -> ToolObservation:
        try:
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
                raise InvalidContract(
                    "stored action no longer matches proposal schema"
                ) from exc

            self.repository.begin_side_effect(
                principal,
                claim,
                now=self.clock.now(),
            )
            observation = self.gateway.execute(
                principal=principal,
                proposal=proposal,
                now=self.clock.now(),
                deadline_at=task.deadline_at,
                idempotency_key=claim.approval_id,
            )
            self.repository.mark_side_effect_executed(
                principal,
                claim,
                now=self.clock.now(),
            )
            PublishOutput.model_validate_json(observation.payload_json)
            with self._execution_lock:
                self._executed_resume[
                    (claim.approval_id, claim.claim_version)
                ] = observation
        except TaskCancelled:
            self._audit(
                principal,
                "task_cancellation_observed",
                {"task_id": claim.task_id, "current_step": "finalize_report"},
            )
            raise
        except RuntimeReferenceError as exc:
            self.repository.record_step_failure(
                principal,
                claim.task_id,
                error_type=exc.code,
                now=self.clock.now(),
            )
            self._audit(
                principal,
                "side_effect_failed",
                {"task_id": claim.task_id, "error_type": exc.code},
            )
            raise
        except Exception as exc:
            normalized = InvalidToolOutput("unexpected resume execution failure")
            self.repository.record_step_failure(
                principal,
                claim.task_id,
                error_type=normalized.code,
                now=self.clock.now(),
            )
            self._audit(
                principal,
                "side_effect_failed",
                {"task_id": claim.task_id, "error_type": normalized.code},
            )
            raise normalized from exc
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

    def _record_task_failure(
        self,
        principal: Principal,
        task_id: str,
        error_type: str,
    ) -> None:
        current = self.repository.get_task(principal, task_id)
        if current.status == "cancelled":
            self._audit(
                principal,
                "task_cancellation_observed",
                {"task_id": task_id, "current_step": current.current_step or "none"},
            )
            raise TaskCancelled(task_id)
        if current.status not in {"failed", "succeeded"}:
            current = self.repository.fail_task(
                principal,
                task_id,
                expected_version=current.version,
                error_type=error_type,
                now=self.clock.now(),
            )
        self._audit(
            principal,
            "task_failed",
            {
                "task_id": task_id,
                "current_step": current.current_step or "none",
                "error_type": error_type,
            },
        )

    @staticmethod
    def _validate(
        model: (
            type[CreateTaskRequest]
            | type[CreateSessionRequest]
            | type[AppendMessageRequest]
            | type[CancelTaskRequest]
            | type[DecisionRequest]
        ),
        payload: Mapping[str, object],
    ):  # type: ignore[no-untyped-def]
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
