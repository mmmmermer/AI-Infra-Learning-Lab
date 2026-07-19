from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .errors import (
    CheckpointMismatch,
    LateTerminalEvent,
    ReplayConflict,
    ReplayGap,
    UnsupportedReplayVersion,
)
from .repository import CurrentStep, RuntimeEvent


EVENT_SCHEMA_VERSION = 1
REDUCER_VERSION = "task-reducer/v1"

_TERMINAL_STATUSES = frozenset({"cancelled", "failed", "succeeded"})
_VALID_STEPS_BY_STATUS: dict[str, frozenset[CurrentStep]] = {
    "pending": frozenset({None}),
    "queued": frozenset({"retrieve_docs", "finalize_report"}),
    "running": frozenset({"retrieve_docs", "draft_report", "finalize_report"}),
    "waiting_approval": frozenset({"human_approval"}),
    "cancelled": frozenset(
        {"retrieve_docs", "draft_report", "human_approval", "finalize_report"}
    ),
    "failed": frozenset(
        {"retrieve_docs", "draft_report", "human_approval", "finalize_report"}
    ),
    "succeeded": frozenset({"finalize_report"}),
}
_OBSERVATIONAL_EVENTS = frozenset(
    {"side_effect_started", "side_effect_executed", "step_failed"}
)
_TRANSITION_EVENTS: dict[
    str,
    tuple[
        tuple[str, CurrentStep],
        tuple[str, CurrentStep],
    ],
] = {
    "task_queued": (
        ("pending", None),
        ("queued", "retrieve_docs"),
    ),
    "initial_worker_claimed": (
        ("queued", "retrieve_docs"),
        ("running", "retrieve_docs"),
    ),
    "retrieval_completed": (
        ("running", "retrieve_docs"),
        ("running", "draft_report"),
    ),
    "approval_requested": (
        ("running", "draft_report"),
        ("waiting_approval", "human_approval"),
    ),
    "approval_approved": (
        ("waiting_approval", "human_approval"),
        ("queued", "finalize_report"),
    ),
    "approval_rejected": (
        ("waiting_approval", "human_approval"),
        ("failed", "human_approval"),
    ),
    "approval_timeout": (
        ("waiting_approval", "human_approval"),
        ("failed", "human_approval"),
    ),
    "resume_claimed": (
        ("queued", "finalize_report"),
        ("running", "finalize_report"),
    ),
    "resume_reclaimed": (
        ("running", "finalize_report"),
        ("running", "finalize_report"),
    ),
    "report_finalized": (
        ("running", "finalize_report"),
        ("succeeded", "finalize_report"),
    ),
}


@dataclass(frozen=True, slots=True)
class TaskReplayState:
    task_id: str
    status: str
    current_step: CurrentStep
    task_version: int
    last_sequence: int
    last_event_fingerprint: str
    applied_event_count: int

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


@dataclass(frozen=True, slots=True)
class TaskCheckpoint:
    reducer_version: str
    event_schema_version: int
    state: TaskReplayState
    state_sha256: str


@dataclass(frozen=True, slots=True)
class ReplayResult:
    state: TaskReplayState
    checkpoint: TaskCheckpoint
    applied_events: int
    ignored_duplicates: int


class TaskEventReducer:
    """Pure, versioned reducer for one task's immutable runtime events."""

    reducer_version = REDUCER_VERSION
    event_schema_version = EVENT_SCHEMA_VERSION

    def replay(
        self,
        events: Iterable[RuntimeEvent],
        *,
        checkpoint: TaskCheckpoint | None = None,
    ) -> ReplayResult:
        state = self._restore(checkpoint) if checkpoint is not None else None
        unique_events, duplicate_count = self._normalize_batch(events)
        applied_count = 0

        for event, fingerprint in unique_events:
            if state is not None and event.sequence <= state.last_sequence:
                if (
                    event.sequence == state.last_sequence
                    and hmac.compare_digest(
                        fingerprint,
                        state.last_event_fingerprint,
                    )
                ):
                    duplicate_count += 1
                    continue
                raise ReplayConflict(
                    "event predates the checkpoint or conflicts with its cursor"
                )

            state = self._apply(state, event, fingerprint)
            applied_count += 1

        if state is None:
            raise ReplayGap("replay requires task_created or a valid checkpoint")

        next_checkpoint = self.checkpoint(state)
        return ReplayResult(
            state=state,
            checkpoint=next_checkpoint,
            applied_events=applied_count,
            ignored_duplicates=duplicate_count,
        )

    def checkpoint(self, state: TaskReplayState) -> TaskCheckpoint:
        self._validate_state(state)
        return TaskCheckpoint(
            reducer_version=self.reducer_version,
            event_schema_version=self.event_schema_version,
            state=state,
            state_sha256=self._state_sha256(state),
        )

    def _restore(self, checkpoint: TaskCheckpoint) -> TaskReplayState:
        if not isinstance(checkpoint, TaskCheckpoint):
            raise CheckpointMismatch("checkpoint has the wrong type")
        if (
            not isinstance(checkpoint.reducer_version, str)
            or checkpoint.reducer_version != self.reducer_version
        ):
            raise UnsupportedReplayVersion("unsupported reducer version")
        if (
            isinstance(checkpoint.event_schema_version, bool)
            or not isinstance(checkpoint.event_schema_version, int)
            or checkpoint.event_schema_version != self.event_schema_version
        ):
            raise UnsupportedReplayVersion("unsupported checkpoint event schema")
        self._validate_state(checkpoint.state)
        expected = self._state_sha256(checkpoint.state)
        if (
            not isinstance(checkpoint.state_sha256, str)
            or len(checkpoint.state_sha256) != 64
            or not hmac.compare_digest(checkpoint.state_sha256, expected)
        ):
            raise CheckpointMismatch("checkpoint state digest does not match")
        return checkpoint.state

    def _normalize_batch(
        self,
        events: Iterable[RuntimeEvent],
    ) -> tuple[list[tuple[RuntimeEvent, str]], int]:
        by_sequence: dict[int, tuple[RuntimeEvent, str]] = {}
        duplicate_count = 0
        for event in events:
            self._validate_event(event)
            fingerprint = self.event_fingerprint(event)
            existing = by_sequence.get(event.sequence)
            if existing is None:
                by_sequence[event.sequence] = (event, fingerprint)
                continue
            if hmac.compare_digest(existing[1], fingerprint):
                duplicate_count += 1
                continue
            raise ReplayConflict("one sequence contains conflicting events")
        return [by_sequence[key] for key in sorted(by_sequence)], duplicate_count

    def _apply(
        self,
        state: TaskReplayState | None,
        event: RuntimeEvent,
        fingerprint: str,
    ) -> TaskReplayState:
        if state is None:
            if (
                event.event_type != "task_created"
                or event.from_status is not None
                or event.to_status != "pending"
                or event.current_step is not None
                or event.task_version != 0
            ):
                raise ReplayGap("the first task event must be task_created at version 0")
            return TaskReplayState(
                task_id=event.task_id,
                status=event.to_status,
                current_step=event.current_step,
                task_version=event.task_version,
                last_sequence=event.sequence,
                last_event_fingerprint=fingerprint,
                applied_event_count=1,
            )

        if event.task_id != state.task_id:
            raise ReplayConflict("a replay batch may contain only one task")
        if state.is_terminal:
            if event.event_type == "report_finalized":
                raise LateTerminalEvent(
                    "a late completion cannot replace a terminal task state"
                )
            raise ReplayConflict("events cannot follow a terminal task state")
        if event.event_type == "task_created":
            raise ReplayConflict("task_created may appear only once")

        if event.event_type in _OBSERVATIONAL_EVENTS:
            self._validate_observation(state, event)
        else:
            self._validate_transition(state, event)

        return TaskReplayState(
            task_id=state.task_id,
            status=event.to_status,
            current_step=event.current_step,
            task_version=event.task_version,
            last_sequence=event.sequence,
            last_event_fingerprint=fingerprint,
            applied_event_count=state.applied_event_count + 1,
        )

    @staticmethod
    def _validate_observation(state: TaskReplayState, event: RuntimeEvent) -> None:
        if event.task_version != state.task_version:
            raise ReplayGap("observational events must retain the task version")
        if (
            event.from_status != state.status
            or event.to_status != state.status
            or event.current_step != state.current_step
        ):
            raise ReplayConflict("observational event changed task state")
        if event.event_type.startswith("side_effect_") and (
            state.status,
            state.current_step,
        ) != ("running", "finalize_report"):
            raise ReplayConflict("side-effect evidence is outside finalize_report")

    @staticmethod
    def _validate_transition(state: TaskReplayState, event: RuntimeEvent) -> None:
        if event.task_version != state.task_version + 1:
            raise ReplayGap("state-changing events must advance exactly one task version")
        if event.from_status != state.status:
            raise ReplayConflict("event from_status does not match replay state")

        if event.event_type in {"task_cancelled", "task_failed"}:
            expected_status = (
                "cancelled" if event.event_type == "task_cancelled" else "failed"
            )
            if (
                event.to_status != expected_status
                or event.current_step != state.current_step
            ):
                raise ReplayConflict("terminal event does not preserve its source step")
            return

        expected = _TRANSITION_EVENTS.get(event.event_type)
        if expected is None:
            raise ReplayConflict("unknown state-changing event type")
        source, target = expected
        if (state.status, state.current_step) != source:
            raise ReplayConflict("event is not valid from the replay state")
        if (event.to_status, event.current_step) != target:
            raise ReplayConflict("event target does not match its event type")

    @staticmethod
    def _validate_event(event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise ReplayConflict("replay input must contain RuntimeEvent values")
        if (
            isinstance(event.schema_version, bool)
            or not isinstance(event.schema_version, int)
            or event.schema_version != EVENT_SCHEMA_VERSION
        ):
            raise UnsupportedReplayVersion("unsupported runtime event schema")
        if (
            isinstance(event.sequence, bool)
            or not isinstance(event.sequence, int)
            or event.sequence <= 0
        ):
            raise ReplayConflict("event sequence must be a positive integer")
        if (
            isinstance(event.task_version, bool)
            or not isinstance(event.task_version, int)
            or event.task_version < 0
        ):
            raise ReplayConflict("task version must be a non-negative integer")
        if (
            not isinstance(event.occurred_at, datetime)
            or event.occurred_at.tzinfo is None
            or event.occurred_at.utcoffset() is None
        ):
            raise ReplayConflict("occurred_at must be a timezone-aware datetime")
        if not isinstance(event.task_id, str) or not event.task_id:
            raise ReplayConflict("task_id must be a non-empty string")
        if not isinstance(event.event_type, str) or not event.event_type:
            raise ReplayConflict("event_type must be a non-empty string")
        if event.from_status is not None and not isinstance(event.from_status, str):
            raise ReplayConflict("from_status must be a string or None")
        if not isinstance(event.to_status, str):
            raise ReplayConflict("to_status must be a string")
        if event.current_step is not None and not isinstance(event.current_step, str):
            raise ReplayConflict("current_step must be a string or None")
        if not isinstance(event.metadata, tuple):
            raise ReplayConflict("event metadata must be an immutable tuple")
        keys: set[str] = set()
        for item in event.metadata:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not all(isinstance(value, str) for value in item)
            ):
                raise ReplayConflict("event metadata must contain string pairs")
            if item[0] in keys:
                raise ReplayConflict("event metadata keys must be unique")
            keys.add(item[0])

    @staticmethod
    def event_fingerprint(event: RuntimeEvent) -> str:
        payload = {
            "schema_version": event.schema_version,
            "sequence": event.sequence,
            "occurred_at": event.occurred_at.isoformat(),
            "task_id": event.task_id,
            "event_type": event.event_type,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "current_step": event.current_step,
            "task_version": event.task_version,
            "metadata": sorted(event.metadata),
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_state(state: TaskReplayState) -> None:
        if not isinstance(state, TaskReplayState):
            raise CheckpointMismatch("checkpoint state has the wrong type")
        if (
            not isinstance(state.task_id, str)
            or not state.task_id
            or not isinstance(state.status, str)
            or state.status not in _VALID_STEPS_BY_STATUS
            or (
                state.current_step is not None
                and not isinstance(state.current_step, str)
            )
            or state.current_step not in _VALID_STEPS_BY_STATUS[state.status]
            or isinstance(state.task_version, bool)
            or not isinstance(state.task_version, int)
            or state.task_version < 0
            or isinstance(state.last_sequence, bool)
            or not isinstance(state.last_sequence, int)
            or state.last_sequence <= 0
            or isinstance(state.applied_event_count, bool)
            or not isinstance(state.applied_event_count, int)
            or state.applied_event_count <= 0
            or state.last_sequence < state.applied_event_count
            or state.task_version + 1 > state.applied_event_count
            or not isinstance(state.last_event_fingerprint, str)
            or len(state.last_event_fingerprint) != 64
            or any(
                character not in "0123456789abcdef"
                for character in state.last_event_fingerprint
            )
        ):
            raise CheckpointMismatch("checkpoint state fields are invalid")

    @staticmethod
    def _state_sha256(state: TaskReplayState) -> str:
        payload = {
            "task_id": state.task_id,
            "status": state.status,
            "current_step": state.current_step,
            "task_version": state.task_version,
            "last_sequence": state.last_sequence,
            "last_event_fingerprint": state.last_event_fingerprint,
            "applied_event_count": state.applied_event_count,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
