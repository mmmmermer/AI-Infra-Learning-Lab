from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pytest

from rag_reference.corpus import Document
from rag_reference.prompting import (
    SYSTEM_INSTRUCTION,
    PromptBoundaryViolation,
    build_prompt_package,
    build_retrieval_audit_record,
    deterministic_mock_generate,
    inspect_retrieval_security,
)
from rag_reference.retrieval import RetrievalResult, build_chunks, retrieve
from rag_reference.security import Principal
from rag_reference.service import RagQueryRequest, ServiceResult


FIXTURES = Path(__file__).parent / "fixtures"


def principal() -> Principal:
    return Principal(
        tenant_id="tenant-demo",
        user_id="sensitive-user-551",
        scopes=frozenset({"rag:query"}),
        effective_permission_groups=frozenset({"public"}),
        acl_version="acl-v1",
    )


def adversarial_documents() -> list[Document]:
    rows = json.loads((FIXTURES / "adversarial_corpus.json").read_text(encoding="utf-8"))
    return [
        Document(
            document_id=row["document_id"],
            permission_group=row["permission_group"],
            text=row["text"],
            source_id=row["source_id"],
            source_version=row["source_version"],
        )
        for row in rows
    ]


def test_poison_hit_is_observable_but_mock_control_flow_never_executes_it():
    chunks = build_chunks(adversarial_documents(), chunk_size=200, overlap=0)
    request = RagQueryRequest("RAG citation secret token", "demo", 3)
    retrieval = retrieve(request.query, chunks, principal(), top_k=3)
    result = ServiceResult(retrieval, "fixture-cache-key", False)

    private_ids = {
        chunk.chunk_id
        for chunk in chunks
        if chunk.permission_group == "compliance_private"
    }
    assert private_ids.isdisjoint(retrieval.scored_chunk_ids)

    package = build_prompt_package(request, principal(), retrieval)
    mock = deterministic_mock_generate(package)
    audit = build_retrieval_audit_record(request, principal(), result)
    audit_json = json.dumps(asdict(audit), sort_keys=True)

    assert package.system_instruction == SYSTEM_INSTRUCTION
    assert package.security_observation.suspected_injection_chunk_count == 1
    assert package.security_observation.unauthorized_chunk_count == 0
    assert mock.tool_calls == ()
    assert mock.ignored_untrusted_instruction_signal_count == 1
    assert "attacker.invalid" not in mock.answer
    assert "secret token" not in mock.answer.lower()
    assert mock.system_instruction_sha256 == sha256(
        SYSTEM_INSTRUCTION.encode("utf-8")
    ).hexdigest()
    assert audit.security_event_codes == ("untrusted_context_injection_signal",)
    assert "attacker.invalid" not in audit_json
    assert "secret token" not in audit_json.lower()
    assert "doc-poison-public" not in audit_json


def test_tampered_unauthorized_context_is_counted_then_blocked_without_log_leak():
    chunks = build_chunks(adversarial_documents(), chunk_size=200, overlap=0)
    private_chunk = next(
        chunk for chunk in chunks if chunk.permission_group == "compliance_private"
    )
    request = RagQueryRequest("sensitive question ALPHA-998", "demo", 1)
    tampered = RetrievalResult(
        chunks=(private_chunk,),
        retrieval_ms=0.0,
        authorized_search_space_size=1,
        scored_chunk_ids=(private_chunk.chunk_id,),
    )
    result = ServiceResult(tampered, "fixture-cache-key", False)

    observation = inspect_retrieval_security(request, principal(), tampered)
    audit_json = json.dumps(
        asdict(build_retrieval_audit_record(request, principal(), result)),
        sort_keys=True,
    )

    assert observation.unauthorized_chunk_count == 1
    assert "unauthorized_context_blocked" in observation.event_codes
    assert '"unauthorized_chunk_count": 1' in audit_json
    assert "unauthorized_context_blocked" in audit_json
    with pytest.raises(PromptBoundaryViolation) as caught:
        build_prompt_package(request, principal(), tampered)
    assert caught.value.observation == observation
    assert "PRIVATE-OMEGA-774" not in str(caught.value)
    assert "PRIVATE-OMEGA-774" not in audit_json
    assert "sensitive question ALPHA-998" not in audit_json
    assert "sensitive-user-551" not in audit_json
