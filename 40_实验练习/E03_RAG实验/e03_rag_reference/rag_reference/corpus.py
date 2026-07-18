from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class Document:
    document_id: str
    permission_group: str
    text: str
    tenant_id: str = "tenant-demo"
    collection_id: str = "demo"
    source_id: str = "self-made-fixture"
    source_version: str = "fixture-v1"

    @property
    def content_sha256(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GoldQuery:
    query_id: str
    query: str
    allowed_groups: frozenset[str]
    expected_document_ids: frozenset[str]
    tenant_id: str = "tenant-demo"
    collection_id: str = "demo"


DOCUMENTS = [
    Document(
        "doc_course_rag_001",
        "public",
        "RAG 先把文档切分成 chunk，再建立检索索引。回答应返回来源引用。chunk 太小可能切断语义，太大可能增加噪声和 token 成本。",
    ),
    Document(
        "doc_exp_scheduler_001",
        "public",
        "SJF 可以降低短任务的平均等待时间，但可能让长任务等待更久。P95 和 P99 用于观察尾部延迟。",
    ),
    Document(
        "doc_compliance_clause_001",
        "public",
        "合规条款要求卖方提供出口合规声明，并在目的地变更时重新检查贸易合规风险。",
    ),
    Document(
        "doc_finance_public_001",
        "finance_public",
        "金融公告样例提到供应链波动和宏观环境不确定性。本材料不构成投资建议。",
    ),
    Document(
        "doc_compliance_private_001",
        "compliance_private",
        "内部合规备忘录指出客户 ZETA 需要额外人工复核。该内容只用于权限实验。",
    ),
]


GOLD_QUERIES = [
    GoldQuery(
        "Q1",
        "RAG 回答为什么需要来源引用？",
        frozenset({"public"}),
        frozenset({"doc_course_rag_001"}),
    ),
    GoldQuery(
        "Q2",
        "SJF 会带来什么副作用？",
        frozenset({"public"}),
        frozenset({"doc_exp_scheduler_001"}),
    ),
    GoldQuery(
        "Q3",
        "卖方在目的地变更时需要做什么？",
        frozenset({"public"}),
        frozenset({"doc_compliance_clause_001"}),
    ),
    GoldQuery(
        "Q4",
        "金融公告提到了哪些风险？",
        frozenset({"public", "finance_public"}),
        frozenset({"doc_finance_public_001"}),
    ),
]
