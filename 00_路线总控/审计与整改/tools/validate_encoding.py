from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".obsidian",
    ".tools",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".lock",
    ".log",
    ".md",
    ".ps1",
    ".py",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {
    ".dockerignore",
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "dockerfile",
    "license",
    "makefile",
}
ALLOWED_TEXT_CONTROLS = {"\t", "\n", "\r"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate repository paths and text files for encoding hazards."
    )
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def is_private_use(character: str) -> bool:
    value = ord(character)
    return (
        0xE000 <= value <= 0xF8FF
        or 0xF0000 <= value <= 0xFFFFD
        or 0x100000 <= value <= 0x10FFFD
    )


def is_noncharacter(character: str) -> bool:
    value = ord(character)
    return 0xFDD0 <= value <= 0xFDEF or value & 0xFFFF in {0xFFFE, 0xFFFF}


def forbidden_character(character: str) -> str | None:
    if character == "\ufffd":
        return "Unicode replacement character U+FFFD"
    if is_private_use(character):
        return f"private-use character U+{ord(character):04X}"
    if is_noncharacter(character):
        return f"Unicode noncharacter U+{ord(character):04X}"
    return None


def relative_label(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    return relative.as_posix() or "."


def issue(
    category: str,
    path: str,
    detail: str,
    *,
    line: int | None = None,
    column: int | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "category": category,
        "severity": "error",
        "path": path,
        "detail": detail,
    }
    if line is not None:
        result["line"] = line
    if column is not None:
        result["column"] = column
    return result


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    directories: list[Path] = []
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in EXCLUDED_PARTS and not name.endswith(".egg-info")
        )
        current_path = Path(current)
        directories.extend(current_path / name for name in directory_names)
        files.extend(current_path / name for name in sorted(file_names))
    return directories, files


def validate_paths(root: Path, paths: list[Path]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    siblings: dict[Path, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for path in paths:
        label = relative_label(path, root)
        name = path.name
        siblings[path.parent][unicodedata.normalize("NFC", name).casefold()].append(name)

        if name.endswith((" ", ".")):
            issues.append(
                issue("unsafe_path_suffix", label, "path component ends with a space or dot")
            )
        if unicodedata.normalize("NFC", name) != name:
            issues.append(issue("path_not_nfc", label, "path component is not Unicode NFC"))

        for column, character in enumerate(name, 1):
            reason = forbidden_character(character)
            if reason:
                issues.append(issue("forbidden_path_character", label, reason, column=column))
            category = unicodedata.category(character)
            if category == "Cc":
                issues.append(
                    issue(
                        "path_control_character",
                        label,
                        f"control character U+{ord(character):04X}",
                        column=column,
                    )
                )

    for parent, keys in sorted(siblings.items(), key=lambda item: str(item[0]).casefold()):
        for names in keys.values():
            distinct = sorted(set(names))
            if len(distinct) > 1:
                parent_label = relative_label(parent, root)
                issues.append(
                    issue(
                        "unicode_or_case_collision",
                        parent_label,
                        f"colliding names after NFC + casefold: {distinct}",
                    )
                )
    return issues


def is_text_file(path: Path) -> bool:
    return path.suffix.casefold() in TEXT_EXTENSIONS or path.name.casefold() in TEXT_NAMES


def validate_text(path: Path, root: Path) -> list[dict[str, object]]:
    label = relative_label(path, root)
    try:
        raw = path.read_bytes()
    except OSError as error:
        return [issue("file_read_error", label, str(error))]

    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        return [
            issue(
                "invalid_utf8",
                label,
                f"byte {error.start}: {error.reason}; UTF-8 or UTF-8 with BOM is required",
            )
        ]

    issues: list[dict[str, object]] = []
    line = 1
    column = 0
    for character in text:
        if character == "\n":
            line += 1
            column = 0
            continue
        column += 1
        reason = forbidden_character(character)
        if reason:
            issues.append(
                issue("forbidden_text_character", label, reason, line=line, column=column)
            )
        if character == "\ufeff":
            issues.append(
                issue(
                    "embedded_bom",
                    label,
                    "U+FEFF appears after the start of the file",
                    line=line,
                    column=column,
                )
            )
        category = unicodedata.category(character)
        if category == "Cc" and character not in ALLOWED_TEXT_CONTROLS:
            issues.append(
                issue(
                    "text_control_character",
                    label,
                    f"control character U+{ord(character):04X}",
                    line=line,
                    column=column,
                )
            )
    return issues


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    args = parse_args()
    root = args.root.resolve(strict=True)
    directories, files = discover(root)
    text_files = [path for path in files if is_text_file(path)]
    issues = validate_paths(root, directories + files)
    for path in text_files:
        issues.extend(validate_text(path, root))

    issues.sort(
        key=lambda item: (
            str(item["path"]).casefold(),
            int(item.get("line", 0)),
            int(item.get("column", 0)),
            str(item["category"]),
        )
    )
    counts = Counter(str(item["category"]) for item in issues)
    report = {
        "schema_version": "1.0",
        "status": "passed" if not issues else "failed",
        "root": ".",
        "directories_scanned": len(directories),
        "files_scanned": len(files),
        "text_files_scanned": len(text_files),
        "issue_count": len(issues),
        "issue_counts": dict(sorted(counts.items())),
        "issues": issues,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        output = args.json_output
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
