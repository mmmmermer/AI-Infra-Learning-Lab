from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MATRIX_RELATIVE = Path("00_路线总控/审计与整改/01_逐文件整改矩阵.csv")
EXPECTED_HEADERS = [
    "file",
    "area",
    "review_state",
    "content_status",
    "implementation_status",
    "verification_status",
    "ownership",
    "instructional_readiness",
    "learner_validation",
    "risk",
    "learning_blocker",
    "action",
    "reason",
    "dependency",
    "acceptance",
]
REQUIRED_NONEMPTY = set(EXPECTED_HEADERS) - {"dependency"}
ALLOWED_REVIEW_STATES = {"unreviewed", "rule-reviewed", "manual-reviewed"}
ALLOWED_CONTENT_STATUSES = {"unassessed", "planned", "draft", "content-reviewed"}
LEGACY_CONTENT_STATUSES = {"reviewed", "待复核"}
ALLOWED_IMPLEMENTATION_STATUSES = {
    "unassessed",
    "not-applicable",
    "absent",
    "partial",
    "runnable-task",
    "executable",
}
ALLOWED_VERIFICATION_STATUSES = {"unassessed", "unverified", "verified"}
ALLOWED_OWNERSHIP = {"unassessed", "reference", "learner-reproduced", "learner-owned"}
ALLOWED_INSTRUCTIONAL_READINESS = {"not-assessed", "partial", "instructional-ready"}
ALLOWED_LEARNER_VALIDATION = {"not-evaluated", "pending", "learner-validated"}
ALLOWED_RISKS = {"unknown", "blocker", "high", "medium", "low"}
ALLOWED_LEARNING_BLOCKERS = {"unknown", "是", "否"}
INCLUDED_EXTENSIONS = {".md", ".py", ".sql", ".toml", ".yaml", ".yml", ".lock", ".ps1"}
INCLUDED_NAMES = {".gitignore", ".dockerignore", "Dockerfile"}
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".obsidian",
    ".tools",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the per-file coverage and automated triage inventory."
    )
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def normalized_relative_path(value: str) -> str:
    return Path(value.replace("\\", "/")).as_posix()


def expected_repository_files(root: Path) -> set[str]:
    expected: set[str] = set()
    for directory, child_directories, filenames in os.walk(root):
        child_directories[:] = [
            name
            for name in child_directories
            if name not in EXCLUDED_DIRECTORY_NAMES and not name.endswith(".egg-info")
        ]
        directory_path = Path(directory)
        for filename in filenames:
            path = directory_path / filename
            if path.suffix.lower() not in INCLUDED_EXTENSIONS and filename not in INCLUDED_NAMES:
                continue
            expected.add(path.relative_to(root).as_posix())
    return expected


def load_matrix(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return headers, rows


def validate(root: Path, matrix_path: Path) -> dict[str, object]:
    errors: list[str] = []
    headers, rows = load_matrix(matrix_path)
    if headers != EXPECTED_HEADERS:
        errors.append(f"matrix headers must be {EXPECTED_HEADERS}; got {headers}")

    files: list[str] = []
    for line_number, row in enumerate(rows, 2):
        missing = sorted(field for field in REQUIRED_NONEMPTY if not row.get(field, ""))
        if missing:
            errors.append(f"matrix line {line_number} has empty required fields: {missing}")

        raw_file = row.get("file", "")
        relative_file = normalized_relative_path(raw_file)
        files.append(relative_file)
        expected_area = relative_file.split("/", 1)[0]
        if row.get("area") != expected_area:
            errors.append(
                f"matrix line {line_number} area {row.get('area')!r} does not match {expected_area!r}"
            )

        review_state = row.get("review_state", "")
        if review_state not in ALLOWED_REVIEW_STATES:
            errors.append(
                f"matrix line {line_number} has invalid review_state {review_state!r}"
            )

        content_status = row.get("content_status", "")
        if content_status in LEGACY_CONTENT_STATUSES:
            errors.append(
                f"matrix line {line_number} uses legacy content status {content_status!r}"
            )
        elif content_status not in ALLOWED_CONTENT_STATUSES:
            errors.append(
                f"matrix line {line_number} has invalid content status {content_status!r}"
            )

        implementation_status = row.get("implementation_status", "")
        verification_status = row.get("verification_status", "")
        if implementation_status not in ALLOWED_IMPLEMENTATION_STATUSES:
            errors.append(
                f"matrix line {line_number} has invalid implementation status "
                f"{implementation_status!r}"
            )
        if verification_status not in ALLOWED_VERIFICATION_STATUSES:
            errors.append(
                f"matrix line {line_number} has invalid verification status {verification_status!r}"
            )
        if implementation_status == "executable" and verification_status != "verified":
            errors.append(
                f"matrix line {line_number} marks executable content without verified evidence"
            )
        if implementation_status in {"absent", "runnable-task"} and verification_status != "unverified":
            errors.append(
                f"matrix line {line_number} has incompatible {implementation_status}/"
                f"{verification_status} states"
            )

        if row.get("ownership") not in ALLOWED_OWNERSHIP:
            errors.append(f"matrix line {line_number} has invalid ownership {row.get('ownership')!r}")
        if row.get("instructional_readiness") not in ALLOWED_INSTRUCTIONAL_READINESS:
            errors.append(
                f"matrix line {line_number} has invalid instructional_readiness "
                f"{row.get('instructional_readiness')!r}"
            )
        if row.get("learner_validation") not in ALLOWED_LEARNER_VALIDATION:
            errors.append(
                f"matrix line {line_number} has invalid learner_validation "
                f"{row.get('learner_validation')!r}"
            )
        if row.get("risk") not in ALLOWED_RISKS:
            errors.append(f"matrix line {line_number} has invalid risk {row.get('risk')!r}")
        if row.get("learning_blocker") not in ALLOWED_LEARNING_BLOCKERS:
            errors.append(
                f"matrix line {line_number} has invalid learning_blocker "
                f"{row.get('learning_blocker')!r}"
            )

        if review_state == "unreviewed":
            expected_unknowns = {
                "content_status": "unassessed",
                "implementation_status": "unassessed",
                "verification_status": "unassessed",
                "ownership": "unassessed",
                "instructional_readiness": "not-assessed",
                "learner_validation": "not-evaluated",
                "risk": "unknown",
                "learning_blocker": "unknown",
            }
            mismatches = {
                field: (row.get(field), expected)
                for field, expected in expected_unknowns.items()
                if row.get(field) != expected
            }
            if mismatches:
                errors.append(
                    f"matrix line {line_number} infers status from an unreviewed file: "
                    f"{mismatches}"
                )
        elif "unassessed" in {
            content_status,
            implementation_status,
            verification_status,
            row.get("ownership", ""),
        }:
            errors.append(
                f"matrix line {line_number} is {review_state} but retains an unassessed core state"
            )

    duplicates = sorted(path for path, count in Counter(files).items() if count > 1)
    if duplicates:
        errors.append(f"matrix contains duplicate file paths: {duplicates}")

    actual_files = set(files)
    expected_files = expected_repository_files(root)
    missing_files = sorted(expected_files - actual_files)
    extra_files = sorted(actual_files - expected_files)
    if missing_files:
        errors.append(f"matrix is missing {len(missing_files)} repository files: {missing_files}")
    if extra_files:
        errors.append(f"matrix references {len(extra_files)} unexpected files: {extra_files}")

    return {
        "status": "failed" if errors else "passed",
        "matrix": matrix_path.relative_to(root).as_posix(),
        "row_count": len(rows),
        "expected_file_count": len(expected_files),
        "review_state_counts": dict(
            sorted(Counter(row.get("review_state", "") for row in rows).items())
        ),
        "content_status_counts": dict(sorted(Counter(row.get("content_status", "") for row in rows).items())),
        "implementation_status_counts": dict(
            sorted(Counter(row.get("implementation_status", "") for row in rows).items())
        ),
        "verification_status_counts": dict(
            sorted(Counter(row.get("verification_status", "") for row in rows).items())
        ),
        "learning_blocker_count": sum(row.get("learning_blocker") == "是" for row in rows),
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    matrix_path = (args.matrix or root / MATRIX_RELATIVE).resolve()
    try:
        report = validate(root, matrix_path)
    except (OSError, csv.Error) as error:
        report = {"status": "failed", "errors": [f"cannot read file matrix: {error}"]}
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
