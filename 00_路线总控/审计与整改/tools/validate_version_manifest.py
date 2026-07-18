from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_RELATIVE = Path(
    "00_路线总控/审计与整改/artifacts/governance/version_manifest.json"
)
ALLOWED_STATUSES = {"active", "review-required", "blocked", "design-only"}
REQUIRED_COMPONENT_IDS = {
    "python",
    "fastapi",
    "pydantic",
    "httpx",
    "pytest",
    "redis-py",
    "redis-server",
    "postgresql",
    "kind",
    "kubernetes",
    "vllm",
    "nvidia-triton-inference-server",
    "openai-triton-language",
    "markdownlint-cli2",
    "zhlint",
    "vale",
    "lychee",
    "codespell",
    "gitleaks",
    "jscpd",
    "mermaid-cli",
    "custom-content-audit",
}
REQUIRED_FIELDS = {
    "component_id",
    "name",
    "category",
    "baseline",
    "status",
    "boundary",
    "source_url",
    "evidence",
    "last_reviewed",
    "max_age_days",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate version baselines and freshness.")
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def valid_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def resolve_evidence(root: Path, raw_path: str) -> str | None:
    candidate = (root / Path(raw_path.replace("\\", "/"))).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return f"evidence path escapes repository root: {raw_path}"
    if not candidate.is_file():
        return f"evidence file does not exist: {raw_path}"
    return None


def validate(root: Path, manifest_path: Path, as_of: date) -> dict[str, object]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "failed", "errors": [f"cannot read version manifest: {error}"]}

    if manifest.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not valid_iso_date(manifest.get("last_updated")):
        errors.append("last_updated must use strict YYYY-MM-DD format")
    default_max_age = manifest.get("default_max_age_days")
    if not isinstance(default_max_age, int) or default_max_age <= 0:
        errors.append("default_max_age_days must be a positive integer")

    components = manifest.get("components")
    if not isinstance(components, list):
        errors.append("components must be a list")
        components = []
    by_id: dict[str, dict[str, object]] = {}
    stale_components: list[dict[str, object]] = []
    for index, component in enumerate(components, 1):
        label = f"component #{index}"
        if not isinstance(component, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(
            field for field in REQUIRED_FIELDS if field not in component or component[field] in ("", [], None)
        )
        if missing:
            errors.append(f"{label} has empty required fields: {missing}")
        component_id = str(component.get("component_id", ""))
        label = component_id or label
        if component_id in by_id:
            errors.append(f"duplicate component_id: {component_id}")
        else:
            by_id[component_id] = component
        status = component.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{label} has invalid status: {status!r}")
        baseline = str(component.get("baseline", ""))
        if baseline == "not-selected" and status not in {"blocked", "design-only", "review-required"}:
            errors.append(f"{label} cannot be active with baseline 'not-selected'")
        source_url = component.get("source_url")
        if not isinstance(source_url, str) or not (
            source_url == "repository-local" or source_url.startswith(("https://", "http://"))
        ):
            errors.append(f"{label} source_url must be HTTP(S) or 'repository-local'")
        reviewed_on = component.get("last_reviewed")
        if not valid_iso_date(reviewed_on):
            errors.append(f"{label} last_reviewed must use strict YYYY-MM-DD format")
        else:
            reviewed_date = date.fromisoformat(str(reviewed_on))
            age_days = (as_of - reviewed_date).days
            max_age = component.get("max_age_days", default_max_age)
            if not isinstance(max_age, int) or max_age <= 0:
                errors.append(f"{label} max_age_days must be a positive integer")
            elif age_days < 0:
                errors.append(f"{label} last_reviewed is in the future relative to {as_of}")
            elif age_days > max_age:
                stale_components.append(
                    {"component_id": component_id, "age_days": age_days, "max_age_days": max_age}
                )
                errors.append(
                    f"{label} is stale: reviewed {age_days} days ago, threshold is {max_age} days"
                )
        evidence = component.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{label} evidence must be a non-empty list")
        else:
            for raw_path in evidence:
                if not isinstance(raw_path, str) or not raw_path.strip():
                    errors.append(f"{label} contains an empty evidence path")
                    continue
                path_error = resolve_evidence(root, raw_path)
                if path_error:
                    errors.append(f"{label}: {path_error}")

    missing_components = sorted(REQUIRED_COMPONENT_IDS - set(by_id))
    if missing_components:
        errors.append(f"required baseline components are missing: {missing_components}")
    return {
        "status": "failed" if errors else "passed",
        "manifest": manifest_path.relative_to(root).as_posix(),
        "as_of": as_of.isoformat(),
        "component_count": len(components),
        "stale_components": stale_components,
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = (args.manifest or root / MANIFEST_RELATIVE).resolve()
    report = validate(root, manifest_path, args.as_of)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
