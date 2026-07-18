from __future__ import annotations

from dataclasses import replace

import pytest

from e04_runtime import Principal, ResourceGrant, VerifiedClaims
from e04_runtime.errors import (
    ApprovalExpired,
    ApprovalTargetMismatch,
    DuplicateDecision,
    InvalidContract,
    InvalidToolOutput,
    InvalidTransition,
    NotFound,
    PermissionDenied,
    StaleClaim,
    VersionConflict,
)

from conftest import Harness, make_principal


def create_waiting(harness: Harness, principal: Principal, *, ttl: int = 300):
    task = harness.runtime.create_task(
        principal,
        {
            "query": "queue approval",
            "collection_id": "infra",
            "deadline_seconds": 600,
        },
    )
    return harness.runtime.run_to_approval(
        principal,
        task.task_id,
        approval_ttl_seconds=ttl,
    )


def decision_payload(approval, decision: str = "approved", comment: str | None = "ok"):
    payload: dict[str, object] = {
        "decision": decision,
        "expected_version": approval.version,
    }
    if comment is not None:
        payload["comment"] = comment
    return payload


def test_run_to_approval_keeps_status_and_current_step_separate(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)

    assert (task.status, task.current_step) == ("waiting_approval", "human_approval")
    assert task.retrieved_source_ids == ("src-public", "src-owner")
    assert approval.target_task_version == task.version
    assert approval.version == 0
    assert approval.status == "pending"
    assert approval.required_approver_capability == "approval:decide"


@pytest.mark.parametrize(
    "forged_field,forged_value",
    [
        ("approver_user_id", "admin"),
        ("tenant_id", "tenant-admin"),
        ("scopes", ["*"]),
        ("workflow_version", "forged"),
        ("draft_sha256", "a" * 64),
        ("action_sha256", "b" * 64),
    ],
)
def test_decision_request_rejects_identity_policy_and_target_fields(
    harness: Harness,
    principal: Principal,
    forged_field: str,
    forged_value: object,
) -> None:
    task, approval = create_waiting(harness, principal)
    payload = decision_payload(approval)
    payload[forged_field] = forged_value

    with pytest.raises(InvalidContract):
        harness.runtime.decide_approval(
            principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=payload,
        )

    assert harness.repository.get_approval(
        principal, task.task_id, approval.approval_id
    ).status == "pending"


def test_approval_persists_normalized_comment_actor_audit_and_outbox(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)

    queued, decided, outbox = harness.runtime.decide_approval(
        principal,
        task_id=task.task_id,
        approval_id=approval.approval_id,
        payload=decision_payload(approval, comment="  looks\n good  "),
    )

    assert (queued.status, queued.current_step) == ("queued", "finalize_report")
    assert decided.status == decided.decision == "approved"
    assert decided.version == 1
    assert decided.comment == "looks good"
    assert decided.approver_user_id == principal.owner_user_id
    assert "approval:decide" in decided.approver_capabilities_snapshot
    assert outbox is not None and outbox.status == "pending"
    assert outbox.approved_task_version == queued.version
    assert outbox.action_sha256 == approval.action_sha256

    approval_event = harness.repository.approval_audit_events[-1]
    assert approval_event.decision == "approved"
    assert approval_event.comment == "looks good"
    assert approval_event.approval_version == 1
    audit_details = dict(harness.audit.records[-1].details)
    assert audit_details["approval_note_present"] == "True"
    assert audit_details["approval_note_length"] == "10"
    assert "looks good" not in str(harness.audit.records)


def test_rejection_requires_comment_and_never_creates_resume_outbox(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)
    with pytest.raises(InvalidContract):
        harness.runtime.decide_approval(
            principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=decision_payload(approval, "rejected", None),
        )

    failed, decided, outbox = harness.runtime.decide_approval(
        principal,
        task_id=task.task_id,
        approval_id=approval.approval_id,
        payload=decision_payload(approval, "rejected", " insufficient citations "),
    )

    assert failed.status == "failed"
    assert failed.current_step == "human_approval"
    assert failed.error_type == "approval_rejected"
    assert decided.status == "rejected"
    assert decided.comment == "insufficient citations"
    assert outbox is None
    assert harness.repository.outbox_for_approval(approval.approval_id) is None
    assert harness.repository.approval_audit_events[-1].decision == "rejected"


def test_expired_decision_commits_timeout_terminal_state_and_audit(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal, ttl=5)
    harness.clock.advance(seconds=5)

    with pytest.raises(ApprovalExpired):
        harness.runtime.decide_approval(
            principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=decision_payload(approval),
        )

    failed = harness.repository.get_task(principal, task.task_id)
    timed_out = harness.repository.get_approval(
        principal, task.task_id, approval.approval_id
    )
    assert failed.status == "failed"
    assert failed.error_type == "approval_timeout"
    assert timed_out.status == timed_out.decision == "timeout"
    assert timed_out.version == 1
    assert timed_out.approver_user_id is None
    assert harness.repository.outbox_for_approval(approval.approval_id) is None
    assert harness.repository.approval_audit_events[-1].decision == "timeout"


def test_reconciler_expires_pending_approval_once(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal, ttl=2)
    harness.clock.advance(seconds=2)

    first = harness.runtime.expire_approvals()
    second = harness.runtime.expire_approvals()

    assert [value.task_id for value in first] == [task.task_id]
    assert second == ()
    assert len(harness.repository.approval_audit_events) == 1
    assert harness.repository.get_approval(
        principal, task.task_id, approval.approval_id
    ).status == "timeout"


def test_duplicate_and_stale_version_decisions_are_rejected(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)
    with pytest.raises(VersionConflict):
        harness.runtime.decide_approval(
            principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload={"decision": "approved", "expected_version": 99},
        )

    harness.runtime.decide_approval(
        principal,
        task_id=task.task_id,
        approval_id=approval.approval_id,
        payload=decision_payload(approval),
    )
    with pytest.raises(DuplicateDecision):
        harness.runtime.decide_approval(
            principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=decision_payload(approval),
        )

    assert len(harness.repository.outbox_records) == 1
    assert len(harness.repository.approval_audit_events) == 1


def test_changed_draft_invalidates_approval_target_without_side_effect(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)
    harness.repository._tasks[task.task_id] = replace(task, draft="tampered")

    with pytest.raises(ApprovalTargetMismatch):
        harness.runtime.decide_approval(
            principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=decision_payload(approval),
        )

    assert harness.repository.get_task(principal, task.task_id).status == "waiting_approval"
    assert harness.repository.outbox_records == ()
    assert harness.publisher.effect_count == 0


def test_decision_requires_server_capability_and_hides_other_owner(
    harness: Harness,
    principal: Principal,
    other_principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)
    no_approval_capability = make_principal(
        capabilities=("rag:query", "report:draft", "report:publish")
    )

    with pytest.raises(PermissionDenied):
        harness.runtime.decide_approval(
            no_approval_capability,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=decision_payload(approval),
        )
    with pytest.raises(NotFound):
        harness.runtime.decide_approval(
            other_principal,
            task_id=task.task_id,
            approval_id=approval.approval_id,
            payload=decision_payload(approval),
        )

    assert harness.repository.get_approval(
        principal, task.task_id, approval.approval_id
    ).status == "pending"


def test_approved_workflow_claims_executes_and_finalizes(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)
    harness.runtime.decide_approval(
        principal,
        task_id=task.task_id,
        approval_id=approval.approval_id,
        payload=decision_payload(approval),
    )

    claim = harness.runtime.claim_resume(worker_id="worker-a")
    assert claim is not None
    observation = harness.runtime.execute_resume(principal, claim)
    completed = harness.runtime.finalize_resume(principal, claim)

    assert observation.tool_name == "publish_report"
    assert completed.status == "succeeded"
    assert completed.current_step == "finalize_report"
    assert harness.publisher.effect_count == 1
    assert harness.repository.outbox_records[0].status == "delivered"
    assert [event.event_type for event in harness.repository.events][-2:] == [
        "resume_claimed",
        "report_finalized",
    ]


def test_expired_claim_is_reclaimed_and_old_worker_is_fenced(
    harness: Harness,
    principal: Principal,
) -> None:
    task, approval = create_waiting(harness, principal)
    harness.runtime.decide_approval(
        principal,
        task_id=task.task_id,
        approval_id=approval.approval_id,
        payload=decision_payload(approval),
    )
    first = harness.runtime.claim_resume(worker_id="worker-a", lease_seconds=1)
    assert first is not None
    harness.runtime.execute_resume(principal, first)
    harness.clock.advance(seconds=1)
    second = harness.runtime.claim_resume(worker_id="worker-b", lease_seconds=5)
    assert second is not None
    assert second.claim_version == first.claim_version + 1

    with pytest.raises(StaleClaim):
        harness.runtime.finalize_resume(principal, first)
    with pytest.raises(InvalidTransition):
        harness.runtime.finalize_resume(principal, second)

    harness.runtime.execute_resume(principal, second)
    completed = harness.runtime.finalize_resume(principal, second)

    assert completed.status == "succeeded"
    assert harness.publisher.effect_count == 1
    assert harness.publisher.calls == 1
    assert "resume_reclaimed" in [event.event_type for event in harness.repository.events]


def test_invalid_runtime_ttl_and_lease_are_rejected_before_state_change(
    harness: Harness,
    principal: Principal,
) -> None:
    task = harness.runtime.create_task(
        principal,
        {
            "query": "queue",
            "collection_id": "infra",
            "deadline_seconds": 60,
        },
    )
    with pytest.raises(InvalidContract):
        harness.runtime.run_to_approval(
            principal,
            task.task_id,
            approval_ttl_seconds=0,
        )
    assert harness.repository.get_task(principal, task.task_id).status == "queued"

    for worker_id, lease_seconds in (("", 30), ("worker", 0), ("worker", True)):
        with pytest.raises(InvalidContract):
            harness.runtime.claim_resume(
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )


def test_empty_authorized_retrieval_fails_without_drafting_or_publishing(
    harness: Harness,
) -> None:
    principal = Principal.from_verified_claims(
        VerifiedClaims(
            tenant_id="tenant-a",
            owner_user_id="owner-a",
            capabilities=(
                "rag:query",
                "report:draft",
                "report:publish",
                "approval:decide",
            ),
            grants=(
                ResourceGrant("rag:query", "infra", ()),
                ResourceGrant("report:draft", "infra", ()),
                ResourceGrant("report:publish", "report/*"),
            ),
        )
    )
    task = harness.runtime.create_task(
        principal,
        {
            "query": "queue",
            "collection_id": "infra",
            "deadline_seconds": 60,
        },
    )

    with pytest.raises(InvalidToolOutput):
        harness.runtime.run_to_approval(principal, task.task_id)

    failed = harness.repository.get_task(principal, task.task_id)
    assert failed.status == "failed"
    assert failed.error_type == "invalid_tool_output"
    assert harness.retriever.calls == 1
    assert harness.publisher.effect_count == 0
