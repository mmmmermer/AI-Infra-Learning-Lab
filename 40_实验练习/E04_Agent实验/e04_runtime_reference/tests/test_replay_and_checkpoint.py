from __future__ import annotations

from dataclasses import replace

import pytest

from e04_runtime import Principal, TaskEventReducer
from e04_runtime.errors import (
    CheckpointMismatch,
    InvalidContract,
    LateTerminalEvent,
    NotFound,
    ReplayConflict,
    ReplayGap,
    UnsupportedReplayVersion,
)

from conftest import Harness


def create_waiting(harness: Harness, principal: Principal):
    task = harness.runtime.create_task(
        principal,
        {
            "query": "replay the workflow",
            "collection_id": "infra",
            "deadline_seconds": 600,
        },
    )
    return harness.runtime.run_to_approval(principal, task.task_id)


def complete_workflow(harness: Harness, principal: Principal):
    waiting, approval = create_waiting(harness, principal)
    queued, _, _ = harness.runtime.decide_approval(
        principal,
        task_id=waiting.task_id,
        approval_id=approval.approval_id,
        payload={
            "decision": "approved",
            "expected_version": approval.version,
            "comment": "ship",
        },
    )
    claim = harness.runtime.claim_resume(
        worker_id="worker-replay",
        tenant_scope=frozenset({principal.tenant_id}),
    )
    assert claim is not None and claim.task_id == queued.task_id
    harness.runtime.execute_resume(principal, claim)
    completed = harness.runtime.finalize_resume(principal, claim)
    return completed


def test_task_events_are_owner_scoped_and_validate_the_cursor(
    harness: Harness,
    principal: Principal,
    other_principal: Principal,
) -> None:
    task = harness.runtime.create_task(
        principal,
        {"query": "events", "collection_id": "infra", "deadline_seconds": 60},
    )
    events = harness.repository.task_events(principal, task.task_id)

    assert [event.event_type for event in events] == ["task_created", "task_queued"]
    assert harness.repository.task_events(
        principal,
        task.task_id,
        after_sequence=events[0].sequence,
    ) == (events[1],)
    with pytest.raises(NotFound):
        harness.repository.task_events(other_principal, task.task_id)
    for invalid_cursor in (True, -1, 1.0, "1"):
        with pytest.raises(InvalidContract):
            harness.repository.task_events(
                principal,
                task.task_id,
                after_sequence=invalid_cursor,  # type: ignore[arg-type]
            )


def test_out_of_order_and_exact_duplicate_events_replay_deterministically(
    harness: Harness,
    principal: Principal,
) -> None:
    waiting, _ = create_waiting(harness, principal)
    events = harness.repository.task_events(principal, waiting.task_id)
    reducer = TaskEventReducer()

    ordered = reducer.replay(events)
    shuffled = reducer.replay((*reversed(events), events[2]))

    assert shuffled.state == ordered.state
    assert shuffled.checkpoint == ordered.checkpoint
    assert shuffled.applied_events == len(events)
    assert shuffled.ignored_duplicates == 1


def test_complete_success_replay_includes_non_versioned_observations(
    harness: Harness,
    principal: Principal,
) -> None:
    completed = complete_workflow(harness, principal)
    events = harness.repository.task_events(principal, completed.task_id)

    result = TaskEventReducer().replay(reversed(events))

    assert result.state.status == "succeeded"
    assert result.state.current_step == "finalize_report"
    assert result.state.task_version == completed.version
    assert result.state.applied_event_count == len(events)
    assert {event.event_type for event in events} >= {
        "side_effect_started",
        "side_effect_executed",
        "report_finalized",
    }


def test_checkpoint_resumes_incrementally_and_deduplicates_cursor_overlap(
    harness: Harness,
    principal: Principal,
) -> None:
    completed = complete_workflow(harness, principal)
    events = harness.repository.task_events(principal, completed.task_id)
    reducer = TaskEventReducer()
    split = 4

    first = reducer.replay(events[:split])
    resumed = reducer.replay(events[split - 1 :], checkpoint=first.checkpoint)
    full = reducer.replay(events)

    assert resumed.state == full.state
    assert resumed.checkpoint == full.checkpoint
    assert resumed.applied_events == len(events) - split
    assert resumed.ignored_duplicates == 1


def test_tampered_checkpoint_digest_is_rejected(
    harness: Harness,
    principal: Principal,
) -> None:
    waiting, _ = create_waiting(harness, principal)
    reducer = TaskEventReducer()
    checkpoint = reducer.replay(
        harness.repository.task_events(principal, waiting.task_id)
    ).checkpoint

    with pytest.raises(CheckpointMismatch):
        reducer.replay((), checkpoint=replace(checkpoint, state_sha256="0" * 64))
    with pytest.raises(CheckpointMismatch):
        reducer.replay(
            (),
            checkpoint=replace(
                checkpoint,
                state=replace(checkpoint.state, current_step="finalize_report"),
            ),
        )
    with pytest.raises(CheckpointMismatch):
        reducer.replay((), checkpoint=replace(checkpoint, state_sha256=None))  # type: ignore[arg-type]
    with pytest.raises(CheckpointMismatch):
        reducer.replay(
            (),
            checkpoint=replace(
                checkpoint,
                state=replace(checkpoint.state, current_step=[]),  # type: ignore[arg-type]
            ),
        )


def test_unsupported_reducer_and_event_versions_are_rejected(
    harness: Harness,
    principal: Principal,
) -> None:
    waiting, _ = create_waiting(harness, principal)
    reducer = TaskEventReducer()
    events = harness.repository.task_events(principal, waiting.task_id)
    checkpoint = reducer.replay(events).checkpoint

    with pytest.raises(UnsupportedReplayVersion):
        reducer.replay((), checkpoint=replace(checkpoint, reducer_version="v2"))
    with pytest.raises(UnsupportedReplayVersion):
        reducer.replay((), checkpoint=replace(checkpoint, event_schema_version=True))
    with pytest.raises(UnsupportedReplayVersion):
        reducer.replay((replace(events[0], schema_version=2),))


def test_conflicting_duplicate_sequence_is_rejected_before_reduction(
    harness: Harness,
    principal: Principal,
) -> None:
    waiting, _ = create_waiting(harness, principal)
    events = harness.repository.task_events(principal, waiting.task_id)
    conflict = replace(events[1], event_type="forged_task_queued")

    with pytest.raises(ReplayConflict, match="conflicting events"):
        TaskEventReducer().replay((events[1], conflict, events[0]))


def test_task_version_gap_is_rejected_without_mutating_prior_checkpoint(
    harness: Harness,
    principal: Principal,
) -> None:
    waiting, _ = create_waiting(harness, principal)
    events = harness.repository.task_events(principal, waiting.task_id)
    reducer = TaskEventReducer()
    initial = reducer.replay((events[0],))
    forged_gap = replace(events[1], task_version=2)

    with pytest.raises(ReplayGap):
        reducer.replay((forged_gap,), checkpoint=initial.checkpoint)
    assert initial.state.status == "pending"
    assert initial.state.task_version == 0
    assert reducer.replay((), checkpoint=initial.checkpoint) == replace(
        initial,
        applied_events=0,
    )


def test_late_completion_after_cancellation_cannot_change_terminal_state(
    harness: Harness,
    principal: Principal,
) -> None:
    task = harness.runtime.create_task(
        principal,
        {"query": "cancel", "collection_id": "infra", "deadline_seconds": 60},
    )
    cancelled = harness.runtime.cancel_task(
        principal,
        task_id=task.task_id,
        payload={"expected_version": task.version, "reason": "operator stop"},
    )
    events = harness.repository.task_events(principal, task.task_id)
    reducer = TaskEventReducer()
    terminal = reducer.replay(events)
    late_completion = replace(
        events[-1],
        sequence=events[-1].sequence + 1,
        event_type="report_finalized",
        from_status="running",
        to_status="succeeded",
        current_step="finalize_report",
        task_version=cancelled.version + 1,
        metadata=(("delivery_id", "late-delivery"),),
    )

    with pytest.raises(LateTerminalEvent):
        reducer.replay((late_completion,), checkpoint=terminal.checkpoint)
    restored = reducer.replay((), checkpoint=terminal.checkpoint).state
    assert (restored.status, restored.task_version) == (
        "cancelled",
        cancelled.version,
    )


def test_mixed_task_event_stream_is_rejected(
    harness: Harness,
    principal: Principal,
) -> None:
    first = harness.runtime.create_task(
        principal,
        {"query": "first", "collection_id": "infra", "deadline_seconds": 60},
    )
    second = harness.runtime.create_task(
        principal,
        {"query": "second", "collection_id": "infra", "deadline_seconds": 60},
    )
    mixed = (
        *harness.repository.task_events(principal, first.task_id),
        *harness.repository.task_events(principal, second.task_id),
    )

    with pytest.raises(ReplayConflict, match="only one task"):
        TaskEventReducer().replay(mixed)
