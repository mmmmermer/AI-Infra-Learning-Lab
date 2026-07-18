from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

import httpx
import pytest

from app.fixed_replay import load_manifest, run_replay, write_results


def write_payload(path: Path, task_type: str = "rag_retrieval") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_type": task_type,
        "priority": 5,
        "estimated_duration_ms": 0,
        "input_json": {"query": "Why do RAG answers need citations?", "top_k": 3},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_manifest(path: Path, rows: list[tuple[str, int, str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["request_id", "planned_offset_ms", "task_type", "payload_ref"])
        writer.writerows(rows)


def test_manifest_validation_and_idempotency_injection(tmp_path: Path) -> None:
    write_payload(tmp_path / "payloads" / "rag.json")
    manifest = tmp_path / "manifest.csv"
    write_manifest(
        manifest,
        [
            ("r001", 0, "rag_retrieval", "payloads/rag.json"),
            ("r002", 10, "rag_retrieval", "payloads/rag.json"),
        ],
    )

    entries = load_manifest(manifest, "run-001")

    assert [entry.payload["idempotency_key"] for entry in entries] == [
        "run-001:r001",
        "run-001:r002",
    ]
    assert all(entry.payload["input_json"]["run_id"] == "run-001" for entry in entries)

    write_manifest(
        manifest,
        [
            ("duplicate", 10, "rag_retrieval", "payloads/rag.json"),
            ("duplicate", 0, "rag_retrieval", "payloads/rag.json"),
        ],
    )
    with pytest.raises(ValueError, match="non-empty and unique"):
        load_manifest(manifest, "run-002")


def test_fixed_schedule_does_not_wait_for_previous_response(tmp_path: Path) -> None:
    write_payload(tmp_path / "payload.json")
    manifest = tmp_path / "manifest.csv"
    write_manifest(
        manifest,
        [
            ("slow", 0, "rag_retrieval", "payload.json"),
            ("next", 5, "rag_retrieval", "payload.json"),
        ],
    )
    entries = load_manifest(manifest, "run-independent")
    events: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_id = body["idempotency_key"].rsplit(":", 1)[-1]
        events.append(f"{request_id}-start")
        if request_id == "slow":
            await asyncio.sleep(0.05)
            events.append("slow-finish")
        return httpx.Response(
            202,
            json={
                "created_new": True,
                "task": {"task_id": f"task-{request_id}", "status": "pending"},
            },
        )

    results = asyncio.run(
        run_replay(
            entries,
            "http://test",
            "test-token",
            transport=httpx.MockTransport(handler),
        )
    )

    assert events.index("slow-start") < events.index("next-start")
    assert events.index("next-start") < events.index("slow-finish")
    assert [result.http_status for result in results] == [202, 202]


def test_terminal_poll_and_csv_export(tmp_path: Path) -> None:
    write_payload(tmp_path / "payload.json")
    manifest = tmp_path / "manifest.csv"
    write_manifest(
        manifest,
        [("r001", 0, "rag_retrieval", "payload.json")],
    )
    entries = load_manifest(manifest, "run-poll")
    polls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "created_new": True,
                    "task": {"task_id": "task-r001", "status": "pending"},
                },
            )
        polls += 1
        return httpx.Response(
            200,
            json={"task_id": "task-r001", "status": "succeeded" if polls > 1 else "running"},
        )

    results = asyncio.run(
        run_replay(
            entries,
            "http://test",
            "test-token",
            poll_interval_seconds=0.001,
            poll_timeout_seconds=0.1,
            transport=httpx.MockTransport(handler),
        )
    )
    output = tmp_path / "results.csv"
    write_results(output, results)

    assert results[0].task_status == "succeeded"
    assert results[0].task_completed_at is not None
    assert output.read_text(encoding="utf-8").startswith("request_id,planned_offset_ms")
