from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .models import TaskCreate


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


@dataclass(frozen=True)
class ReplayEntry:
    request_id: str
    planned_offset_ms: int
    task_type: str
    payload_ref: str
    payload: dict[str, Any]


@dataclass
class ReplayResult:
    request_id: str
    planned_offset_ms: int
    planned_start_at: str
    actual_start_at: str
    start_lateness_ms: float
    response_at: str | None = None
    api_latency_ms: float | None = None
    http_status: int | None = None
    task_id: str | None = None
    created_new: bool | None = None
    task_status: str | None = None
    task_completed_at: str | None = None
    total_observed_ms: float | None = None
    error_type: str | None = None
    error_detail: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def load_manifest(path: Path, run_id: str) -> list[ReplayEntry]:
    manifest_path = path.resolve()
    payload_root = manifest_path.parent
    entries: list[ReplayEntry] = []
    seen_request_ids: set[str] = set()
    previous_offset = -1

    with manifest_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"request_id", "planned_offset_ms", "task_type", "payload_ref"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"manifest must contain columns: {sorted(required)}")

        for line_number, row in enumerate(reader, start=2):
            request_id = (row.get("request_id") or "").strip()
            task_type = (row.get("task_type") or "").strip()
            payload_ref = (row.get("payload_ref") or "").strip()
            if not request_id or request_id in seen_request_ids:
                raise ValueError(f"line {line_number}: request_id must be non-empty and unique")
            seen_request_ids.add(request_id)

            try:
                planned_offset_ms = int(row.get("planned_offset_ms") or "")
            except ValueError as error:
                raise ValueError(
                    f"line {line_number}: planned_offset_ms must be an integer"
                ) from error
            if planned_offset_ms < 0 or planned_offset_ms < previous_offset:
                raise ValueError(
                    f"line {line_number}: planned offsets must be non-negative and non-decreasing"
                )
            previous_offset = planned_offset_ms

            payload_path = (payload_root / payload_ref).resolve()
            if not payload_path.is_relative_to(payload_root):
                raise ValueError(f"line {line_number}: payload_ref escapes the manifest directory")
            with payload_path.open(encoding="utf-8") as payload_source:
                payload = json.load(payload_source)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number}: payload must be a JSON object")
            if "idempotency_key" in payload:
                raise ValueError(
                    f"line {line_number}: payload must not set idempotency_key; replay injects it"
                )
            if payload.get("task_type") != task_type:
                raise ValueError(
                    f"line {line_number}: manifest task_type does not match payload"
                )

            replay_payload = dict(payload)
            input_json = dict(replay_payload.get("input_json") or {})
            input_json["run_id"] = run_id
            replay_payload["input_json"] = input_json
            replay_payload["idempotency_key"] = f"{run_id}:{request_id}"
            validated = TaskCreate.model_validate(replay_payload).model_dump(mode="json")
            entries.append(
                ReplayEntry(
                    request_id=request_id,
                    planned_offset_ms=planned_offset_ms,
                    task_type=task_type,
                    payload_ref=payload_ref,
                    payload=validated,
                )
            )

    if not entries:
        raise ValueError("manifest must contain at least one request")
    return entries


async def _poll_task(
    client: httpx.AsyncClient,
    task_id: str,
    headers: dict[str, str],
    poll_interval_seconds: float,
    poll_timeout_seconds: float,
) -> tuple[str | None, str | None, str | None]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + poll_timeout_seconds
    while loop.time() < deadline:
        await asyncio.sleep(poll_interval_seconds)
        response = await client.get(f"/tasks/{task_id}", headers=headers)
        if response.status_code != 200:
            return None, "poll_http_error", f"GET task returned {response.status_code}"
        body = response.json()
        status = body.get("status")
        if status in TERMINAL_STATUSES:
            if status == "succeeded":
                return str(status), None, None
            return str(status), str(body.get("error_type") or f"task_{status}"), None
    return None, "poll_timeout", "task did not reach a terminal state before timeout"


async def _send_entry(
    client: httpx.AsyncClient,
    entry: ReplayEntry,
    headers: dict[str, str],
    start_monotonic: float,
    start_wall: datetime,
    poll_interval_seconds: float,
    poll_timeout_seconds: float,
) -> ReplayResult:
    loop = asyncio.get_running_loop()
    target_monotonic = start_monotonic + entry.planned_offset_ms / 1_000
    await asyncio.sleep(max(0.0, target_monotonic - loop.time()))

    actual_monotonic = loop.time()
    actual_wall = _utc_now()
    planned_wall = start_wall + timedelta(milliseconds=entry.planned_offset_ms)
    result = ReplayResult(
        request_id=entry.request_id,
        planned_offset_ms=entry.planned_offset_ms,
        planned_start_at=_iso(planned_wall),
        actual_start_at=_iso(actual_wall),
        start_lateness_ms=max(0.0, (actual_monotonic - target_monotonic) * 1_000),
    )

    try:
        response = await client.post("/tasks", json=entry.payload, headers=headers)
        response_monotonic = loop.time()
        response_wall = _utc_now()
        result.response_at = _iso(response_wall)
        result.api_latency_ms = (response_monotonic - actual_monotonic) * 1_000
        result.http_status = response.status_code
        if response.status_code != 202:
            result.error_type = "submit_http_error"
            result.error_detail = response.text[:500]
            return result

        body = response.json()
        task = body.get("task") or {}
        result.task_id = task.get("task_id")
        result.task_status = task.get("status")
        result.created_new = body.get("created_new")
        if not result.task_id:
            result.error_type = "invalid_submit_response"
            result.error_detail = "202 response did not contain task.task_id"
            return result

        if poll_timeout_seconds > 0:
            status, error_type, error_detail = await _poll_task(
                client,
                result.task_id,
                headers,
                poll_interval_seconds,
                poll_timeout_seconds,
            )
            if status is not None:
                completed_monotonic = loop.time()
                completed_wall = _utc_now()
                result.task_status = status
                result.task_completed_at = _iso(completed_wall)
                result.total_observed_ms = (
                    completed_monotonic - actual_monotonic
                ) * 1_000
                result.error_type = error_type
                result.error_detail = error_detail
            else:
                result.error_type = error_type
                result.error_detail = error_detail
        return result
    except (httpx.HTTPError, ValueError) as error:
        result.error_type = type(error).__name__
        result.error_detail = str(error)[:500]
        return result


async def run_replay(
    entries: list[ReplayEntry],
    base_url: str,
    bearer_token: str,
    poll_interval_seconds: float = 0.25,
    poll_timeout_seconds: float = 0.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[ReplayResult]:
    if not bearer_token:
        raise ValueError("bearer_token must not be empty")
    if poll_interval_seconds <= 0 or poll_timeout_seconds < 0:
        raise ValueError("poll interval must be positive and timeout must be non-negative")

    headers = {"Authorization": f"Bearer {bearer_token}"}
    limits = httpx.Limits(
        max_connections=max(10, len(entries)),
        max_keepalive_connections=max(10, len(entries)),
    )
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=30,
        limits=limits,
        transport=transport,
    ) as client:
        loop = asyncio.get_running_loop()
        start_monotonic = loop.time()
        start_wall = _utc_now()
        tasks = [
            asyncio.create_task(
                _send_entry(
                    client,
                    entry,
                    headers,
                    start_monotonic,
                    start_wall,
                    poll_interval_seconds,
                    poll_timeout_seconds,
                )
            )
            for entry in entries
        ]
        return await asyncio.gather(*tasks)


def write_results(path: Path, results: list[ReplayResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a fixed P03 arrival manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--base-url",
        default=os.getenv("P03_REPLAY_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--run-id", default=os.getenv("P03_REPLAY_RUN_ID", "manual"))
    parser.add_argument("--poll-interval-seconds", type=float, default=0.25)
    parser.add_argument("--poll-timeout-seconds", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bearer_token = os.getenv("P03_REPLAY_BEARER_TOKEN")
    if not bearer_token:
        raise SystemExit("P03_REPLAY_BEARER_TOKEN is required")
    entries = load_manifest(args.manifest, args.run_id)
    results = asyncio.run(
        run_replay(
            entries,
            args.base_url,
            bearer_token,
            args.poll_interval_seconds,
            args.poll_timeout_seconds,
        )
    )
    write_results(args.output, results)
    summary = {
        "request_count": len(results),
        "submit_success_count": sum(result.http_status == 202 for result in results),
        "terminal_success_count": sum(
            result.task_status == "succeeded" for result in results
        ),
        "error_count": sum(result.error_type is not None for result in results),
        "max_start_lateness_ms": max(result.start_lateness_ms for result in results),
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
