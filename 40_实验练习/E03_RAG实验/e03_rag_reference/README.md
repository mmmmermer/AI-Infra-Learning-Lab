# E03 RAG Reference

Deterministic BM25 reference with a fixed corpus, independent gold queries, actual retrieval timing, and tenant/authorization pre-filtering.

The request parser accepts business fields only: `query`, `collection_id`, and `top_k`.
Verified identity is passed separately as a server-owned `Principal`; request payloads that try
to supply tenant, user, permission, or reviewer fields fail with status semantics `422`.
Authorization is applied before BM25 scoring. The optional in-memory cache binds each entry to
tenant, effective ACL fingerprint/version, collection/version, query, top-k, and retrieval version.
The ingestion fixture rejects client-supplied tenant, collection, ACL, and provenance metadata;
a trusted collection policy assigns them server-side. Prompt packaging keeps retrieved chunks in
an explicit `untrusted_retrieved_data` role, while audit records retain hashes and counts rather
than raw query, document text, user ID, or credentials.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python examples\run_evaluation.py
```

This project evaluates retrieval, trusted-metadata assignment, prompt role separation, and audit
redaction only. It does not call a model, invent generation latency, or claim behavioral resistance
to prompt injection without a real generation call and adversarial output evaluation. Citation,
reranker, model behavior, deletion propagation, and production identity-provider checks remain
explicit downstream acceptance items, not capabilities claimed by this reference.
