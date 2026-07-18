from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tomllib
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate published JSON, TOML, and CSV files with structured parsers."
    )
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def repository_files(root: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
    )
    relative_paths = result.stdout.decode("utf-8").split("\0")
    return sorted(
        root / relative
        for relative in relative_paths
        if relative
        and (root / relative).is_file()
        and (root / relative).suffix.lower() in {".json", ".toml", ".csv"}
    )


def validate_json(path: Path) -> None:
    json.loads(path.read_text(encoding="utf-8-sig"))


def validate_toml(path: Path) -> None:
    tomllib.loads(path.read_text(encoding="utf-8-sig"))


def validate_csv(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError("CSV is empty") from error
        if not header or not any(cell.strip() for cell in header):
            raise ValueError("CSV header is empty")
        expected_width = len(header)
        for line_number, row in enumerate(reader, 2):
            if not row or not any(cell.strip() for cell in row):
                raise ValueError(f"blank CSV record at logical row {line_number}")
            if len(row) != expected_width:
                raise ValueError(
                    f"CSV row {line_number} has {len(row)} columns; expected {expected_width}"
                )


def validate(root: Path) -> dict[str, object]:
    errors: list[str] = []
    counts: Counter[str] = Counter()
    validators = {".json": validate_json, ".toml": validate_toml, ".csv": validate_csv}
    for path in repository_files(root):
        suffix = path.suffix.lower()
        counts[suffix.removeprefix(".")] += 1
        try:
            validators[suffix](path)
        except (OSError, UnicodeError, ValueError, csv.Error, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
            errors.append(f"{path.relative_to(root).as_posix()}: {error}")
    return {
        "status": "failed" if errors else "passed",
        "file_counts": dict(sorted(counts.items())),
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    try:
        report = validate(args.root.resolve())
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        report = {"status": "failed", "file_counts": {}, "errors": [str(error)]}
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
