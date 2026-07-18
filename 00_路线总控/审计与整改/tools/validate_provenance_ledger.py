from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LEDGER_RELATIVE = Path(
    "00_路线总控/审计与整改/artifacts/governance/provenance_license_ledger.csv"
)
EXPECTED_HEADERS = [
    "asset_id",
    "asset_class",
    "scope",
    "origin_or_source",
    "version_or_revision",
    "license_or_terms",
    "modification_status",
    "redistribution_decision",
    "evidence_paths",
    "last_reviewed",
    "review_status",
    "notes",
]
REQUIRED_CLASSES = {
    "authored-content",
    "reference-code",
    "data-or-fixture",
    "dependency",
    "tool",
    "external-material",
    "generated-artifact",
}
ALLOWED_REVIEW_STATUSES = {"verified", "review-required", "prohibited"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the provenance and license ledger.")
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def resolve_evidence(root: Path, raw_path: str) -> str | None:
    candidate = (root / Path(raw_path.replace("\\", "/"))).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return f"evidence path escapes repository root: {raw_path}"
    if not candidate.is_file():
        return f"evidence file does not exist: {raw_path}"
    return None


def validate(root: Path, ledger_path: Path) -> dict[str, object]:
    errors: list[str] = []
    with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if headers != EXPECTED_HEADERS:
        errors.append(f"ledger headers must be {EXPECTED_HEADERS}; got {headers}")
    seen_ids: set[str] = set()
    classes: set[str] = set()
    for line_number, row in enumerate(rows, 2):
        missing = [header for header in EXPECTED_HEADERS if not row.get(header, "")]
        if missing:
            errors.append(f"ledger line {line_number} has empty required fields: {missing}")
        asset_id = row.get("asset_id", "")
        if asset_id in seen_ids:
            errors.append(f"duplicate asset_id: {asset_id}")
        seen_ids.add(asset_id)
        classes.add(row.get("asset_class", ""))
        review_status = row.get("review_status", "")
        if review_status not in ALLOWED_REVIEW_STATUSES:
            errors.append(f"{asset_id} has invalid review_status: {review_status!r}")
        license_value = row.get("license_or_terms", "").lower()
        if license_value in {"unknown", "review-required"} and review_status != "review-required":
            errors.append(f"{asset_id} has unknown terms but is not marked review-required")
        if review_status == "review-required" and row.get("redistribution_decision", "").lower() == "approved":
            errors.append(f"{asset_id} cannot be approved while review is required")
        reviewed_on = row.get("last_reviewed", "")
        try:
            if date.fromisoformat(reviewed_on).isoformat() != reviewed_on:
                raise ValueError
        except ValueError:
            errors.append(f"{asset_id} has invalid last_reviewed: {reviewed_on!r}")
        for raw_path in filter(None, (item.strip() for item in row.get("evidence_paths", "").split(";"))):
            path_error = resolve_evidence(root, raw_path)
            if path_error:
                errors.append(f"{asset_id}: {path_error}")
    missing_classes = sorted(REQUIRED_CLASSES - classes)
    if missing_classes:
        errors.append(f"ledger does not cover required asset classes: {missing_classes}")
    review_required_count = sum(
        row.get("review_status") == "review-required" for row in rows
    )
    verified_count = sum(row.get("review_status") == "verified" for row in rows)
    return {
        "status": (
            "failed"
            if errors
            else "inventory-passed-with-review-required"
            if review_required_count
            else "passed"
        ),
        "ledger": ledger_path.relative_to(root).as_posix(),
        "row_count": len(rows),
        "asset_classes": sorted(classes),
        "verified_count": verified_count,
        "review_required_count": review_required_count,
        "redistribution_fully_approved": not errors and review_required_count == 0,
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    ledger_path = (args.ledger or root / LEDGER_RELATIVE).resolve()
    try:
        report = validate(root, ledger_path)
    except OSError as error:
        report = {"status": "failed", "errors": [f"cannot read provenance ledger: {error}"]}
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
