from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
import re

from rank_bm25 import BM25Okapi

from .models import TaskRecord


@dataclass(frozen=True)
class Document:
    tenant_id: str
    document_id: str
    permission_group: str
    text: str


@dataclass(frozen=True)
class Chunk:
    tenant_id: str
    chunk_id: str
    document_id: str
    permission_group: str
    text: str


@dataclass(frozen=True)
class GoldQuery:
    query_id: str
    tenant_id: str
    permission_groups: tuple[str, ...]
    query: str
    expected_document_id: str


DOCUMENTS = (
    Document(
        "tenant-reference",
        "doc_course_rag_001",
        "public",
        "RAG 先把文档切分成 chunk，再建立检索索引。回答应返回来源引用。chunk 太小可能切断语义，太大可能增加噪声和 token 成本。",
    ),
    Document(
        "tenant-reference",
        "doc_exp_scheduler_001",
        "public",
        "SJF 可以降低短任务的平均等待时间，但可能让长任务等待更久。P95 和 P99 用于观察尾部延迟。",
    ),
    Document(
        "tenant-reference",
        "doc_compliance_clause_001",
        "public",
        "合规条款要求卖方提供出口合规声明，并在目的地变更时重新检查贸易合规风险。",
    ),
    Document(
        "tenant-reference",
        "doc_finance_public_001",
        "finance_public",
        "金融公告样例提到供应链波动和宏观环境不确定性。本材料不构成投资建议。",
    ),
    Document(
        "tenant-reference",
        "doc_compliance_private_001",
        "compliance_private",
        "内部合规备忘录指出客户 ZETA 需要额外人工复核。该内容只用于权限实验。",
    ),
    Document(
        "tenant-other",
        "doc_other_tenant_001",
        "public",
        "OMEGA 项目的跨租户测试文档只属于 tenant-other，不得返回给其他租户。",
    ),
)

GOLD_QUERIES = (
    GoldQuery(
        "Q1",
        "tenant-reference",
        ("public",),
        "RAG 回答为什么需要来源引用？",
        "doc_course_rag_001",
    ),
    GoldQuery(
        "Q2",
        "tenant-reference",
        ("public",),
        "SJF 会带来什么副作用？",
        "doc_exp_scheduler_001",
    ),
    GoldQuery(
        "Q3",
        "tenant-reference",
        ("compliance_private", "public"),
        "客户 ZETA 为什么需要额外人工复核？",
        "doc_compliance_private_001",
    ),
    GoldQuery(
        "Q4",
        "tenant-other",
        ("public",),
        "OMEGA 项目的文档属于哪个租户？",
        "doc_other_tenant_001",
    ),
)


def tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text.lower())
    if not normalized:
        return []
    if len(normalized) == 1:
        return [normalized]
    return [normalized[index : index + 2] for index in range(len(normalized) - 1)]


def build_chunks(
    documents: tuple[Document, ...], chunk_size: int = 80, overlap: int = 10
) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    step = chunk_size - overlap
    for document in documents:
        for index, start in enumerate(range(0, len(document.text), step)):
            text = document.text[start : start + chunk_size]
            if not text:
                break
            chunks.append(
                Chunk(
                    tenant_id=document.tenant_id,
                    chunk_id=f"{document.document_id}#chunk-{index:03d}",
                    document_id=document.document_id,
                    permission_group=document.permission_group,
                    text=text,
                )
            )
            if start + chunk_size >= len(document.text):
                break
    return tuple(chunks)


CHUNKS = build_chunks(DOCUMENTS)


def execute_rag_retrieval(task: TaskRecord) -> dict:
    query = task.input_json.get("query")
    top_k = task.input_json.get("top_k", 3)
    if not isinstance(query, str) or not query.strip():
        raise ValueError("invalid_rag_input")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
        raise ValueError("invalid_rag_input")

    started = perf_counter_ns()
    allowed_groups = frozenset(task.allowed_permission_groups)
    authorized_chunks = [
        chunk
        for chunk in CHUNKS
        if chunk.tenant_id == task.tenant_id
        and chunk.permission_group in allowed_groups
    ]
    if authorized_chunks:
        bm25 = BM25Okapi([tokenize(chunk.text) for chunk in authorized_chunks])
        query_tokens = set(tokenize(query))
        scores = bm25.get_scores(list(query_tokens))
        ranked = sorted(
            (
                (
                    chunk,
                    float(score),
                    len(query_tokens.intersection(tokenize(chunk.text))),
                )
                for chunk, score in zip(authorized_chunks, scores, strict=True)
            ),
            key=lambda item: (-float(item[1]), item[0].chunk_id),
        )
        selected = [item for item in ranked if item[2] > 0][:top_k]
    else:
        selected = []
    retrieval_ms = (perf_counter_ns() - started) / 1_000_000

    sources = [
        {
            "tenant_id": chunk.tenant_id,
            "document_id": chunk.document_id,
            "chunk_id": chunk.chunk_id,
            "permission_group": chunk.permission_group,
            "text": chunk.text,
            "retrieval_score": score,
            "matched_query_token_count": matched_query_token_count,
        }
        for chunk, score, matched_query_token_count in selected
    ]
    answer = None
    if sources:
        answer = "\n\n".join(
            f"[{source['document_id']}] {source['text']}" for source in sources
        )
    retrieval_status = "ok"
    if not authorized_chunks:
        retrieval_status = "empty_authorized_corpus"
    elif not sources:
        retrieval_status = "no_relevant_authorized_source"
    return {
        "kind": "rag_retrieval_reference",
        "answer_mode": "deterministic_extractive",
        "quality_status": "retrieval_only_not_llm_evaluated",
        "query": query,
        "answer": answer,
        "retrieval_ms": retrieval_ms,
        "retrieval_status": retrieval_status,
        "authorized_search_space_size": len(authorized_chunks),
        "security_context": {
            "tenant_id": task.tenant_id,
            "user_id": task.user_id,
            "allowed_permission_groups": list(task.allowed_permission_groups),
        },
        "sources": sources,
    }
