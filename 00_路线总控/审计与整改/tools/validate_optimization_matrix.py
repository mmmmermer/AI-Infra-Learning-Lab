from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AUDIT_RELATIVE = Path("00_路线总控/审计与整改")
MATRIX_RELATIVE = AUDIT_RELATIVE / "11_教材内容优化任务矩阵.csv"
EVIDENCE_RELATIVE = (
    AUDIT_RELATIVE / "artifacts/governance/optimization_matrix_status_evidence.csv"
)
EXPECTED_HEADERS = [
    "task_id",
    "workstream",
    "module",
    "chapter",
    "current_strength",
    "knowledge_gap",
    "explanation_gap",
    "target_engineering_level",
    "target_research_level",
    "target_finance_level",
    "action",
    "priority",
    "prerequisites",
    "expected_artifact",
    "acceptance",
    "canonical_sources",
    "status",
]
EVIDENCE_HEADERS = ["task_id", "status", "reason", "evidence_paths", "reviewed_on"]
TASK_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-\d{3}$")
TASK_REFERENCE_PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]*-\d{3})(?!\d)")
TASK_RANGE_PATTERN = re.compile(
    r"(?P<prefix>[A-Z][A-Z0-9]*)-(?P<start>\d{3})\s*"
    r"(?:至|\.\.|~|–|—)\s*(?:(?P=prefix)-)?(?P<end>\d{3})"
)
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_STATUSES = {"planned", "in-progress", "blocked", "completed", "cancelled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the 110-row optimization matrix.")
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return headers, rows


def referenced_task_ids(value: str) -> set[str]:
    references = {match.group(1) for match in TASK_REFERENCE_PATTERN.finditer(value)}
    for match in TASK_RANGE_PATTERN.finditer(value):
        start = int(match.group("start"))
        end = int(match.group("end"))
        if start <= end and end - start <= 999:
            references.update(
                f"{match.group('prefix')}-{number:03d}" for number in range(start, end + 1)
            )
    return references


def descriptive_prerequisites(value: str) -> list[str]:
    descriptions: list[str] = []
    for part in re.split(r"[;；]", value):
        item = TASK_RANGE_PATTERN.sub("", part)
        item = TASK_REFERENCE_PATTERN.sub("", item).strip(" ,，:+")
        if item and item != "无":
            descriptions.append(item)
    return descriptions


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    state: dict[str, int] = defaultdict(int)
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dependency in sorted(graph.get(node, set())):
            if dependency not in graph:
                continue
            if state[dependency] == 0:
                visit(dependency)
            elif state[dependency] == 1:
                start = stack.index(dependency)
                cycle = stack[start:] + [dependency]
                body = cycle[:-1]
                rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
                canonical = min(rotations)
                cycles.add(canonical + (canonical[0],))
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if state[node] == 0:
            visit(node)
    return [list(cycle) for cycle in sorted(cycles)]


def resolve_evidence_path(root: Path, value: str) -> tuple[Path | None, str | None]:
    candidate = (root / Path(value.replace("\\", "/"))).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None, f"evidence path escapes repository root: {value}"
    if not candidate.is_file():
        return None, f"evidence file does not exist: {value}"
    return candidate, None


def validate(
    root: Path,
    matrix_path: Path,
    evidence_path: Path,
    expected_rows: int = 110,
) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    headers, rows = load_csv(matrix_path)
    if headers != EXPECTED_HEADERS:
        errors.append(
            f"matrix headers must be the fixed 17-column schema; got {len(headers)} columns: {headers}"
        )
    if len(rows) != expected_rows:
        errors.append(f"matrix must contain {expected_rows} rows; got {len(rows)}")

    by_id: dict[str, dict[str, str]] = {}
    duplicate_ids: list[str] = []
    for line_number, row in enumerate(rows, 2):
        missing = [header for header in EXPECTED_HEADERS if not row.get(header, "").strip()]
        if missing:
            errors.append(f"matrix line {line_number} has empty required fields: {missing}")
        task_id = row.get("task_id", "")
        if not TASK_ID_PATTERN.fullmatch(task_id):
            errors.append(f"matrix line {line_number} has invalid task_id: {task_id!r}")
        if task_id in by_id:
            duplicate_ids.append(task_id)
        else:
            by_id[task_id] = row
        if row.get("priority") not in ALLOWED_PRIORITIES:
            errors.append(
                f"{task_id or f'line {line_number}'} has invalid priority: {row.get('priority')!r}"
            )
        if row.get("status") not in ALLOWED_STATUSES:
            errors.append(
                f"{task_id or f'line {line_number}'} has invalid status: {row.get('status')!r}"
            )
    if duplicate_ids:
        errors.append(f"duplicate task IDs: {sorted(set(duplicate_ids))}")

    graph: dict[str, set[str]] = {}
    external_prerequisites: dict[str, list[str]] = {}
    for task_id, row in by_id.items():
        dependencies = referenced_task_ids(row["prerequisites"])
        graph[task_id] = dependencies
        descriptions = descriptive_prerequisites(row["prerequisites"])
        if descriptions:
            external_prerequisites[task_id] = descriptions
        for dependency in sorted(dependencies):
            if dependency not in by_id:
                errors.append(f"{task_id} references missing internal prerequisite {dependency}")
                continue
            if row["priority"] == "P0" and by_id[dependency]["priority"] in {"P2", "P3"}:
                errors.append(
                    f"P0 task {task_id} depends on lower-scheduled {by_id[dependency]['priority']} task "
                    f"{dependency}"
                )
            if row["status"] == "completed" and by_id[dependency]["status"] != "completed":
                errors.append(
                    f"completed task {task_id} has unmet prerequisite {dependency} "
                    f"with status {by_id[dependency]['status']}"
                )

    cycles = find_cycles(graph)
    for cycle in cycles:
        errors.append(f"dependency cycle: {' -> '.join(cycle)}")

    evidence_by_id: dict[str, dict[str, str]] = {}
    if not evidence_path.is_file():
        errors.append(f"status evidence table does not exist: {evidence_path}")
    else:
        evidence_headers, evidence_rows = load_csv(evidence_path)
        if evidence_headers != EVIDENCE_HEADERS:
            errors.append(
                f"status evidence headers must be {EVIDENCE_HEADERS}; got {evidence_headers}"
            )
        for line_number, record in enumerate(evidence_rows, 2):
            task_id = record.get("task_id", "")
            if not task_id:
                errors.append(f"status evidence line {line_number} has no task_id")
                continue
            if task_id in evidence_by_id:
                errors.append(f"duplicate status evidence for {task_id}")
                continue
            evidence_by_id[task_id] = record
            if task_id not in by_id:
                errors.append(f"status evidence references unknown task {task_id}")
                continue
            if record.get("status") != by_id[task_id]["status"]:
                errors.append(
                    f"status evidence for {task_id} says {record.get('status')!r}, "
                    f"matrix says {by_id[task_id]['status']!r}"
                )
            reviewed_on = record.get("reviewed_on", "")
            try:
                if date.fromisoformat(reviewed_on).isoformat() != reviewed_on:
                    raise ValueError
            except ValueError:
                errors.append(f"status evidence for {task_id} has invalid reviewed_on: {reviewed_on!r}")
            for raw_path in filter(None, (item.strip() for item in record.get("evidence_paths", "").split(";"))):
                _, path_error = resolve_evidence_path(root, raw_path)
                if path_error:
                    errors.append(f"{task_id}: {path_error}")

    for task_id, row in by_id.items():
        record = evidence_by_id.get(task_id)
        if row["status"] == "blocked":
            if record is None or not record.get("reason", "").strip():
                errors.append(f"blocked task {task_id} must have a reason in the status evidence table")
        if row["status"] == "completed":
            if record is None or not record.get("evidence_paths", "").strip():
                errors.append(f"completed task {task_id} must have evidence paths in the status evidence table")

    if external_prerequisites:
        warnings.append(
            f"{len(external_prerequisites)} tasks retain descriptive external prerequisites; "
            "these are reported but are not treated as matrix task IDs"
        )
    return {
        "status": "failed" if errors else "passed",
        "matrix": matrix_path.relative_to(root).as_posix(),
        "row_count": len(rows),
        "column_count": len(headers),
        "task_id_count": len(by_id),
        "dependency_edge_count": sum(len(items) for items in graph.values()),
        "dependency_graph": {task_id: sorted(items) for task_id, items in sorted(graph.items())},
        "cycles": cycles,
        "external_prerequisites": external_prerequisites,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    matrix_path = (args.matrix or root / MATRIX_RELATIVE).resolve()
    evidence_path = (args.evidence or root / EVIDENCE_RELATIVE).resolve()
    report = validate(root, matrix_path, evidence_path)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
