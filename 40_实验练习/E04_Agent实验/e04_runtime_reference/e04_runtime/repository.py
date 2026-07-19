from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import RLock

from .errors import (
    ApprovalExpired,
    ApprovalTargetMismatch,
    DuplicateDecision,
    InvalidContract,
    InvalidTransition,
    NotFound,
    PermissionDenied,
    StaleClaim,
    TaskCancelled,
    VersionConflict,
)
from .models import DecisionRequest, Principal, ResumeClaim
from .tools import sha256_text


TaskStatus = str
CurrentStep = str | None


@dataclass(frozen=True, slots=True)
class AgentTask:
    task_id: str
    tenant_id: str
    owner_user_id: str
    query: str
    collection_id: str
    workflow_version: str
    deadline_at: datetime
    status: TaskStatus
    current_step: CurrentStep
    version: int
    retrieved_source_ids: tuple[str, ...] = ()
    draft: str | None = None
    draft_sha256: str | None = None
    action_json: str | None = None
    action_sha256: str | None = None
    approval_id: str | None = None
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    task_id: str
    tenant_id: str
    owner_user_id: str
    workflow_version: str
    draft_sha256: str
    action_sha256: str
    target_task_version: int
    required_approver_capability: str
    version: int
    status: str
    expires_at: datetime
    decision: str | None = None
    comment: str | None = None
    approver_user_id: str | None = None
    approver_capabilities_snapshot: tuple[str, ...] = ()
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResumeOutbox:
    outbox_id: str
    approval_id: str
    task_id: str
    approved_task_version: int
    action_sha256: str
    status: str
    claim_owner: str | None = None
    claim_version: int = 0
    claimed_task_version: int | None = None
    lease_until: datetime | None = None
    effect_started: bool = False
    effect_executed: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    sequence: int
    occurred_at: datetime
    task_id: str
    event_type: str
    from_status: str | None
    to_status: str
    current_step: CurrentStep
    task_version: int
    schema_version: int = 1
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ApprovalAuditEvent:
    sequence: int
    occurred_at: datetime
    approval_id: str
    task_id: str
    decision: str
    approval_version: int
    approver_user_id: str | None
    comment: str | None


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: str
    tenant_id: str
    owner_user_id: str
    version: int
    messages: tuple[str, ...]


ALLOWED_TASK_TRANSITIONS: dict[
    tuple[str, CurrentStep], set[tuple[str, CurrentStep]]
] = {
    ("pending", None): {("queued", "retrieve_docs")},
    ("queued", "retrieve_docs"): {("running", "retrieve_docs")},
    ("running", "retrieve_docs"): {("running", "draft_report")},
    ("running", "draft_report"): {("waiting_approval", "human_approval")},
    ("waiting_approval", "human_approval"): {
        ("queued", "finalize_report"),
        ("failed", "human_approval"),
    },
    ("queued", "finalize_report"): {("running", "finalize_report")},
    ("running", "finalize_report"): {
        ("running", "finalize_report"),
        ("succeeded", "finalize_report"),
    },
}


class InMemoryRepository:
    """Single-process teaching repository. The RLock is the transaction boundary."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: dict[str, AgentTask] = {}
        self._approvals: dict[str, Approval] = {}
        self._outbox: dict[str, ResumeOutbox] = {}
        self._outbox_by_approval: dict[str, str] = {}
        self._events: list[RuntimeEvent] = []
        self._approval_audit_events: list[ApprovalAuditEvent] = []
        self._sessions: dict[tuple[str, str, str], SessionState] = {}
        self._task_sequence = 0
        self._approval_sequence = 0
        self._outbox_sequence = 0

    def create_task(
        self,
        *,
        principal: Principal,
        query: str,
        collection_id: str,
        workflow_version: str,
        deadline_at: datetime,
        now: datetime,
    ) -> AgentTask:
        with self._lock:
            self._task_sequence += 1
            task_id = f"task-{self._task_sequence:03d}"
            task = AgentTask(
                task_id=task_id,
                tenant_id=principal.tenant_id,
                owner_user_id=principal.owner_user_id,
                query=query,
                collection_id=collection_id,
                workflow_version=workflow_version,
                deadline_at=deadline_at,
                status="pending",
                current_step=None,
                version=0,
            )
            self._tasks[task_id] = task
            self._append_event_locked(now, task, "task_created", None)
            return self._transition_locked(
                task,
                expected_version=0,
                status="queued",
                current_step="retrieve_docs",
                event_type="task_queued",
                now=now,
            )

    def get_task(self, principal: Principal, task_id: str) -> AgentTask:
        with self._lock:
            return self._owned_task_locked(principal, task_id)

    def task_events(
        self,
        principal: Principal,
        task_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[RuntimeEvent, ...]:
        if (
            isinstance(after_sequence, bool)
            or not isinstance(after_sequence, int)
            or after_sequence < 0
        ):
            raise InvalidContract("after_sequence must be a non-negative integer")
        with self._lock:
            self._owned_task_locked(principal, task_id)
            return tuple(
                event
                for event in self._events
                if event.task_id == task_id and event.sequence > after_sequence
            )

    def assert_active(
        self,
        principal: Principal,
        task_id: str,
        *,
        expected_version: int,
    ) -> AgentTask:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            if task.status == "cancelled":
                raise TaskCancelled(task_id)
            if task.status in {"failed", "succeeded"}:
                raise InvalidTransition("task is terminal")
            if task.version != expected_version:
                raise VersionConflict("task version changed")
            return task

    def cancel_task(
        self,
        principal: Principal,
        task_id: str,
        *,
        expected_version: int,
        reason_present: bool,
        reason_length: int,
        now: datetime,
    ) -> AgentTask:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            if task.version != expected_version:
                raise VersionConflict("task version changed")
            if task.status == "cancelled":
                raise TaskCancelled("task is already cancelled")
            if task.status in {"failed", "succeeded"}:
                raise InvalidTransition("task is terminal")

            approval = (
                self._approvals.get(task.approval_id)
                if task.approval_id is not None
                else None
            )
            outbox_id = (
                self._outbox_by_approval.get(task.approval_id)
                if task.approval_id is not None
                else None
            )
            outbox = self._outbox.get(outbox_id) if outbox_id is not None else None
            if outbox is not None and (
                outbox.effect_started
                or outbox.effect_executed
                or outbox.status == "delivered"
            ):
                raise InvalidTransition("side effect execution has already started")

            if approval is not None and approval.status == "pending":
                cancelled_approval = replace(
                    approval,
                    version=approval.version + 1,
                    status="cancelled",
                    decision="cancelled",
                    decided_at=now,
                )
                self._approvals[approval.approval_id] = cancelled_approval
                self._append_approval_audit_locked(now, cancelled_approval)
            if outbox is not None and outbox.status in {"pending", "claimed"}:
                self._outbox[outbox.outbox_id] = replace(
                    outbox,
                    status="cancelled",
                    claim_owner=None,
                    claimed_task_version=None,
                    lease_until=None,
                )

            cancelled = replace(
                task,
                status="cancelled",
                version=task.version + 1,
                error_type="task_cancelled",
            )
            self._tasks[task_id] = cancelled
            self._append_event_locked(
                now,
                cancelled,
                "task_cancelled",
                task.status,
                metadata=(
                    ("reason_present", str(reason_present).lower()),
                    ("reason_length", str(reason_length)),
                ),
            )
            return cancelled

    def claim_initial(
        self,
        principal: Principal,
        task_id: str,
        *,
        expected_version: int,
        now: datetime,
    ) -> AgentTask:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            return self._transition_locked(
                task,
                expected_version=expected_version,
                status="running",
                current_step="retrieve_docs",
                event_type="initial_worker_claimed",
                now=now,
            )

    def record_retrieval(
        self,
        principal: Principal,
        task_id: str,
        *,
        expected_version: int,
        source_ids: tuple[str, ...],
        now: datetime,
    ) -> AgentTask:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            return self._transition_locked(
                task,
                expected_version=expected_version,
                status="running",
                current_step="draft_report",
                event_type="retrieval_completed",
                now=now,
                retrieved_source_ids=source_ids,
            )

    def create_waiting_approval(
        self,
        principal: Principal,
        task_id: str,
        *,
        expected_version: int,
        draft: str,
        action_json: str,
        action_sha256: str,
        expires_at: datetime,
        now: datetime,
    ) -> tuple[AgentTask, Approval]:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            self._approval_sequence += 1
            approval_id = f"approval-{self._approval_sequence:03d}"
            draft_sha256 = sha256_text(draft)
            updated = self._transition_locked(
                task,
                expected_version=expected_version,
                status="waiting_approval",
                current_step="human_approval",
                event_type="approval_requested",
                now=now,
                draft=draft,
                draft_sha256=draft_sha256,
                action_json=action_json,
                action_sha256=action_sha256,
                approval_id=approval_id,
            )
            approval = Approval(
                approval_id=approval_id,
                task_id=task_id,
                tenant_id=task.tenant_id,
                owner_user_id=task.owner_user_id,
                workflow_version=task.workflow_version,
                draft_sha256=draft_sha256,
                action_sha256=action_sha256,
                target_task_version=updated.version,
                required_approver_capability="approval:decide",
                version=0,
                status="pending",
                expires_at=expires_at,
            )
            self._approvals[approval_id] = approval
            return updated, approval

    def decide_approval(
        self,
        principal: Principal,
        *,
        task_id: str,
        approval_id: str,
        request: DecisionRequest,
        now: datetime,
    ) -> tuple[AgentTask, Approval, ResumeOutbox | None]:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            approval = self._owned_approval_locked(principal, task_id, approval_id)
            if approval.status != "pending":
                raise DuplicateDecision()

            if now >= approval.expires_at:
                failed = self._expire_approval_locked(task, approval, now)
                raise ApprovalExpired(failed.task_id)

            if approval.version != request.expected_version:
                raise VersionConflict("approval version changed")
            if task.status != "waiting_approval" or task.current_step != "human_approval":
                raise InvalidTransition("task is not waiting for approval")
            if approval.required_approver_capability not in principal.capabilities:
                raise PermissionDenied("approver capability is missing")
            self._validate_approval_target_locked(task, approval)

            if request.decision == "rejected":
                failed = self._transition_locked(
                    task,
                    expected_version=task.version,
                    status="failed",
                    current_step="human_approval",
                    event_type="approval_rejected",
                    now=now,
                    error_type="approval_rejected",
                )
                decided = replace(
                    approval,
                    version=approval.version + 1,
                    status="rejected",
                    decision="rejected",
                    comment=request.comment,
                    approver_user_id=principal.owner_user_id,
                    approver_capabilities_snapshot=tuple(sorted(principal.capabilities)),
                    decided_at=now,
                )
                self._approvals[approval_id] = decided
                self._append_approval_audit_locked(now, decided)
                return failed, decided, None

            if approval_id in self._outbox_by_approval:
                raise DuplicateDecision("resume outbox already exists")
            queued = self._transition_locked(
                task,
                expected_version=task.version,
                status="queued",
                current_step="finalize_report",
                event_type="approval_approved",
                now=now,
            )
            decided = replace(
                approval,
                version=approval.version + 1,
                status="approved",
                decision="approved",
                comment=request.comment,
                approver_user_id=principal.owner_user_id,
                approver_capabilities_snapshot=tuple(sorted(principal.capabilities)),
                decided_at=now,
            )
            self._approvals[approval_id] = decided
            self._append_approval_audit_locked(now, decided)
            self._outbox_sequence += 1
            outbox = ResumeOutbox(
                outbox_id=f"outbox-{self._outbox_sequence:03d}",
                approval_id=approval_id,
                task_id=task_id,
                approved_task_version=queued.version,
                action_sha256=approval.action_sha256,
                status="pending",
            )
            self._outbox[outbox.outbox_id] = outbox
            self._outbox_by_approval[approval_id] = outbox.outbox_id
            return queued, decided, outbox

    def expire_pending_approvals(self, *, now: datetime) -> tuple[AgentTask, ...]:
        expired: list[AgentTask] = []
        with self._lock:
            for approval in tuple(self._approvals.values()):
                if approval.status != "pending" or now < approval.expires_at:
                    continue
                task = self._tasks[approval.task_id]
                if task.status == "waiting_approval":
                    expired.append(self._expire_approval_locked(task, approval, now))
            return tuple(expired)

    def claim_resume(
        self,
        *,
        worker_id: str,
        tenant_scope: frozenset[str],
        now: datetime,
        lease_seconds: int,
    ) -> ResumeClaim | None:
        with self._lock:
            for outbox in sorted(self._outbox.values(), key=lambda value: value.outbox_id):
                pending = outbox.status == "pending"
                reclaimable = (
                    outbox.status == "claimed"
                    and outbox.lease_until is not None
                    and outbox.lease_until <= now
                )
                if not pending and not reclaimable:
                    continue

                task = self._tasks[outbox.task_id]
                if task.tenant_id not in tenant_scope:
                    continue
                if pending:
                    if (
                        task.status != "queued"
                        or task.current_step != "finalize_report"
                        or task.version != outbox.approved_task_version
                    ):
                        raise StaleClaim("resume payload no longer matches queued task")
                else:
                    if (
                        task.status != "running"
                        or task.current_step != "finalize_report"
                        or task.version != outbox.claimed_task_version
                    ):
                        raise StaleClaim("expired claim no longer matches running task")

                claimed_task = self._transition_locked(
                    task,
                    expected_version=task.version,
                    status="running",
                    current_step="finalize_report",
                    event_type="resume_claimed" if pending else "resume_reclaimed",
                    now=now,
                    allow_reclaim=reclaimable,
                )
                claimed = replace(
                    outbox,
                    status="claimed",
                    claim_owner=worker_id,
                    claim_version=outbox.claim_version + 1,
                    claimed_task_version=claimed_task.version,
                    lease_until=now + timedelta(seconds=lease_seconds),
                )
                self._outbox[outbox.outbox_id] = claimed
                return ResumeClaim(
                    outbox_id=claimed.outbox_id,
                    task_id=claimed.task_id,
                    approval_id=claimed.approval_id,
                    tenant_id=task.tenant_id,
                    owner_user_id=task.owner_user_id,
                    worker_id=worker_id,
                    claim_version=claimed.claim_version,
                    task_version=claimed_task.version,
                    lease_until=claimed.lease_until,
                )
            return None

    def validate_resume_claim(
        self,
        principal: Principal,
        claim: ResumeClaim,
        *,
        now: datetime,
    ) -> tuple[AgentTask, ResumeOutbox]:
        with self._lock:
            task = self._owned_task_locked(principal, claim.task_id)
            outbox = self._outbox.get(claim.outbox_id)
            if outbox is None:
                raise StaleClaim()
            self._validate_claim_locked(task, outbox, claim, now)
            return task, outbox

    def begin_side_effect(
        self,
        principal: Principal,
        claim: ResumeClaim,
        *,
        now: datetime,
    ) -> ResumeOutbox:
        """Atomically fence hard cancellation before entering an external handler."""
        with self._lock:
            task = self._owned_task_locked(principal, claim.task_id)
            outbox = self._outbox.get(claim.outbox_id)
            if outbox is None:
                raise StaleClaim()
            self._validate_claim_locked(task, outbox, claim, now)
            if outbox.effect_started:
                return outbox
            updated = replace(outbox, effect_started=True)
            self._outbox[outbox.outbox_id] = updated
            self._append_event_locked(
                now,
                task,
                "side_effect_started",
                task.status,
            )
            return updated

    def mark_side_effect_executed(
        self,
        principal: Principal,
        claim: ResumeClaim,
        *,
        now: datetime,
    ) -> ResumeOutbox:
        with self._lock:
            task = self._owned_task_locked(principal, claim.task_id)
            outbox = self._outbox.get(claim.outbox_id)
            if outbox is None:
                raise StaleClaim()
            self._validate_claim_locked(
                task,
                outbox,
                claim,
                now,
                allow_expired_lease=True,
            )
            if not outbox.effect_started:
                raise InvalidTransition("side effect has not started")
            if outbox.effect_executed:
                return outbox
            updated = replace(outbox, effect_executed=True)
            self._outbox[outbox.outbox_id] = updated
            self._append_event_locked(
                now,
                task,
                "side_effect_executed",
                task.status,
            )
            return updated

    def record_step_failure(
        self,
        principal: Principal,
        task_id: str,
        *,
        error_type: str,
        now: datetime,
    ) -> None:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            if task.status == "cancelled":
                raise TaskCancelled(task_id)
            if task.status in {"failed", "succeeded"}:
                return
            self._append_event_locked(
                now,
                task,
                "step_failed",
                task.status,
                metadata=(("error_type", error_type),),
            )

    def finalize_resume(
        self,
        principal: Principal,
        claim: ResumeClaim,
        *,
        delivery_id: str,
        now: datetime,
    ) -> AgentTask:
        with self._lock:
            task = self._owned_task_locked(principal, claim.task_id)
            outbox = self._outbox.get(claim.outbox_id)
            if outbox is None:
                raise StaleClaim()
            self._validate_claim_locked(task, outbox, claim, now)
            completed = self._transition_locked(
                task,
                expected_version=claim.task_version,
                status="succeeded",
                current_step="finalize_report",
                event_type="report_finalized",
                now=now,
                metadata=(("delivery_id", delivery_id),),
            )
            self._outbox[outbox.outbox_id] = replace(
                outbox,
                status="delivered",
                lease_until=None,
            )
            return completed

    def outbox_for_approval(self, approval_id: str) -> ResumeOutbox | None:
        with self._lock:
            outbox_id = self._outbox_by_approval.get(approval_id)
            return self._outbox.get(outbox_id) if outbox_id is not None else None

    def get_approval(self, principal: Principal, task_id: str, approval_id: str) -> Approval:
        with self._lock:
            self._owned_task_locked(principal, task_id)
            return self._owned_approval_locked(principal, task_id, approval_id)

    def fail_task(
        self,
        principal: Principal,
        task_id: str,
        *,
        expected_version: int,
        error_type: str,
        now: datetime,
    ) -> AgentTask:
        with self._lock:
            task = self._owned_task_locked(principal, task_id)
            if task.status == "cancelled":
                raise TaskCancelled(task_id)
            if task.status in {"succeeded", "failed"}:
                raise InvalidTransition("task is terminal")
            if task.version != expected_version:
                raise VersionConflict()
            failed = replace(task, status="failed", version=task.version + 1, error_type=error_type)
            self._tasks[task_id] = failed
            self._append_event_locked(
                now,
                failed,
                "task_failed",
                task.status,
                metadata=(("error_type", error_type),),
            )
            return failed

    def create_session(
        self,
        principal: Principal,
        *,
        session_id: str,
    ) -> SessionState:
        key = (principal.tenant_id, principal.owner_user_id, session_id)
        with self._lock:
            if key in self._sessions:
                raise InvalidTransition("session already exists")
            state = SessionState(
                session_id=session_id,
                tenant_id=principal.tenant_id,
                owner_user_id=principal.owner_user_id,
                version=0,
                messages=(),
            )
            self._sessions[key] = state
            return state

    def get_session(self, principal: Principal, session_id: str) -> SessionState:
        key = (principal.tenant_id, principal.owner_user_id, session_id)
        with self._lock:
            try:
                return self._sessions[key]
            except KeyError as exc:
                raise NotFound("session not found") from exc

    def append_session_message(
        self,
        principal: Principal,
        *,
        session_id: str,
        expected_version: int,
        text: str,
    ) -> SessionState:
        key = (principal.tenant_id, principal.owner_user_id, session_id)
        with self._lock:
            try:
                state = self._sessions[key]
            except KeyError as exc:
                raise NotFound("session not found") from exc
            if state.version != expected_version:
                raise VersionConflict("session version changed")
            updated = replace(
                state,
                version=state.version + 1,
                messages=(*state.messages, text),
            )
            self._sessions[key] = updated
            return updated

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def approval_audit_events(self) -> tuple[ApprovalAuditEvent, ...]:
        with self._lock:
            return tuple(self._approval_audit_events)

    @property
    def outbox_records(self) -> tuple[ResumeOutbox, ...]:
        with self._lock:
            return tuple(self._outbox.values())

    def _owned_task_locked(self, principal: Principal, task_id: str) -> AgentTask:
        task = self._tasks.get(task_id)
        if (
            task is None
            or task.tenant_id != principal.tenant_id
            or task.owner_user_id != principal.owner_user_id
        ):
            raise NotFound("task not found")
        return task

    def _owned_approval_locked(
        self,
        principal: Principal,
        task_id: str,
        approval_id: str,
    ) -> Approval:
        approval = self._approvals.get(approval_id)
        if (
            approval is None
            or approval.task_id != task_id
            or approval.tenant_id != principal.tenant_id
            or approval.owner_user_id != principal.owner_user_id
        ):
            raise NotFound("approval not found")
        return approval

    def _transition_locked(
        self,
        task: AgentTask,
        *,
        expected_version: int,
        status: str,
        current_step: CurrentStep,
        event_type: str,
        now: datetime,
        allow_reclaim: bool = False,
        metadata: tuple[tuple[str, str], ...] = (),
        **changes: object,
    ) -> AgentTask:
        if task.status == "cancelled":
            raise TaskCancelled(task.task_id)
        if task.version != expected_version:
            raise VersionConflict()
        source = (task.status, task.current_step)
        target = (status, current_step)
        if target not in ALLOWED_TASK_TRANSITIONS.get(source, set()):
            if not (allow_reclaim and source == target == ("running", "finalize_report")):
                raise InvalidTransition(f"{source} -> {target}")
        updated = replace(
            task,
            status=status,
            current_step=current_step,
            version=task.version + 1,
            **changes,
        )
        self._tasks[task.task_id] = updated
        self._append_event_locked(now, updated, event_type, task.status, metadata)
        return updated

    def _append_event_locked(
        self,
        now: datetime,
        task: AgentTask,
        event_type: str,
        from_status: str | None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._events.append(
            RuntimeEvent(
                sequence=len(self._events) + 1,
                occurred_at=now,
                task_id=task.task_id,
                event_type=event_type,
                from_status=from_status,
                to_status=task.status,
                current_step=task.current_step,
                task_version=task.version,
                metadata=metadata,
            )
        )

    def _expire_approval_locked(
        self,
        task: AgentTask,
        approval: Approval,
        now: datetime,
    ) -> AgentTask:
        failed = self._transition_locked(
            task,
            expected_version=task.version,
            status="failed",
            current_step="human_approval",
            event_type="approval_timeout",
            now=now,
            error_type="approval_timeout",
        )
        self._approvals[approval.approval_id] = replace(
            approval,
            version=approval.version + 1,
            status="timeout",
            decision="timeout",
            decided_at=now,
        )
        self._append_approval_audit_locked(
            now,
            self._approvals[approval.approval_id],
        )
        return failed

    @staticmethod
    def _validate_approval_target_locked(
        task: AgentTask,
        approval: Approval,
    ) -> None:
        current_draft_hash = sha256_text(task.draft or "")
        current_action_hash = sha256_text(task.action_json or "")
        expected = (
            task.workflow_version,
            current_draft_hash,
            current_action_hash,
        )
        stored = (
            approval.workflow_version,
            approval.draft_sha256,
            approval.action_sha256,
        )
        if expected != stored or task.version != approval.target_task_version:
            raise ApprovalTargetMismatch()

    def _append_approval_audit_locked(
        self,
        now: datetime,
        approval: Approval,
    ) -> None:
        if approval.decision is None:
            raise ValueError("approval audit requires a decision")
        self._approval_audit_events.append(
            ApprovalAuditEvent(
                sequence=len(self._approval_audit_events) + 1,
                occurred_at=now,
                approval_id=approval.approval_id,
                task_id=approval.task_id,
                decision=approval.decision,
                approval_version=approval.version,
                approver_user_id=approval.approver_user_id,
                comment=approval.comment,
            )
        )

    @staticmethod
    def _validate_claim_locked(
        task: AgentTask,
        outbox: ResumeOutbox,
        claim: ResumeClaim,
        now: datetime,
        *,
        allow_expired_lease: bool = False,
    ) -> None:
        if task.status == "cancelled":
            raise TaskCancelled(task.task_id)
        if (
            claim.tenant_id != task.tenant_id
            or claim.owner_user_id != task.owner_user_id
            or outbox.status != "claimed"
            or outbox.claim_owner != claim.worker_id
            or outbox.claim_version != claim.claim_version
            or outbox.claimed_task_version != claim.task_version
            or task.version != claim.task_version
            or task.status != "running"
            or task.current_step != "finalize_report"
            or outbox.lease_until is None
            or (not allow_expired_lease and outbox.lease_until <= now)
        ):
            raise StaleClaim()
