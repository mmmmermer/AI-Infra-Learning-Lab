from __future__ import annotations

from datetime import UTC, datetime

import pytest

from e04_runtime import Principal, RedactedAuditLog
from e04_runtime.errors import InvalidContract, NotFound, VersionConflict

from conftest import Harness


def test_session_request_rejects_identity_fields(
    harness: Harness,
    principal: Principal,
) -> None:
    with pytest.raises(InvalidContract):
        harness.runtime.create_session(
            principal,
            {"session_id": "session-1", "tenant_id": "forged"},
        )


def test_sessions_are_scoped_by_tenant_owner_and_session_id(
    harness: Harness,
    principal: Principal,
    other_principal: Principal,
) -> None:
    first = harness.runtime.create_session(principal, {"session_id": "shared"})
    second = harness.runtime.create_session(other_principal, {"session_id": "shared"})
    harness.runtime.append_session_message(
        principal,
        session_id=first.session_id,
        payload={"text": "private weather context", "expected_version": 0},
    )

    assert harness.repository.get_session(principal, "shared").messages == (
        "private weather context",
    )
    assert harness.repository.get_session(other_principal, "shared") == second
    assert second.messages == ()

    with pytest.raises(NotFound):
        harness.repository.get_session(other_principal, "owner-only")


def test_cross_owner_session_is_hidden_as_not_found(
    harness: Harness,
    principal: Principal,
    other_principal: Principal,
) -> None:
    harness.runtime.create_session(principal, {"session_id": "owner-only"})

    with pytest.raises(NotFound):
        harness.repository.get_session(other_principal, "owner-only")
    with pytest.raises(NotFound):
        harness.runtime.append_session_message(
            other_principal,
            session_id="owner-only",
            payload={"text": "forged write", "expected_version": 0},
        )


def test_session_compare_and_set_prevents_lost_update(
    harness: Harness,
    principal: Principal,
) -> None:
    harness.runtime.create_session(principal, {"session_id": "session-cas"})
    updated = harness.runtime.append_session_message(
        principal,
        session_id="session-cas",
        payload={"text": "first", "expected_version": 0},
    )

    with pytest.raises(VersionConflict):
        harness.runtime.append_session_message(
            principal,
            session_id="session-cas",
            payload={"text": "stale", "expected_version": 0},
        )

    assert updated.version == 1
    assert harness.repository.get_session(principal, "session-cas").messages == ("first",)


def test_operational_audit_redacts_sensitive_values_and_newlines(
    harness: Harness,
    principal: Principal,
) -> None:
    secret_message = "Bearer real-looking-token\nprivate prompt"
    harness.runtime.create_session(principal, {"session_id": "audit"})
    harness.runtime.append_session_message(
        principal,
        session_id="audit",
        payload={"text": secret_message, "expected_version": 0},
    )
    record = harness.audit.records[-1]

    assert dict(record.details)["message"] == "[REDACTED]"
    assert secret_message not in str(harness.audit.records)
    assert principal.tenant_id not in record.tenant_hash
    assert principal.owner_user_id not in record.subject_hash


def test_redacted_audit_defensively_redacts_approval_comment_key(
    principal: Principal,
) -> None:
    audit = RedactedAuditLog()
    record = audit.append(
        occurred_at=datetime.now(UTC),
        event_type="test",
        principal=principal,
        details={"approval_comment": "sensitive review note"},
    )

    assert dict(record.details)["approval_comment"] == "[REDACTED]"
