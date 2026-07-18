from __future__ import annotations

import argparse
import ast
import json
import re
import textwrap
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXCLUDED_PARTS = {
    ".git",
    ".obsidian",
    ".tools",
    ".venv",
    ".pytest_cache",
    "__pycache__",
}
FENCE_PATTERN = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
STALE_P03_VERSION_PATTERN = re.compile(r"\bP03\s+v0\.3(?!\.1)\b")
LEGACY_RAG_ROUTE = "/rag/query"
LEGACY_ROUTE_EXCEPTIONS = {
    Path("40_实验练习/E06_数据库异步任务实验/E06-02 文档解析与 RAG 请求异步化.md")
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate repository Markdown and WikiLinks.")
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    return parser.parse_args()


def included(path: Path) -> bool:
    return not any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in path.parts)


def markdown_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.md") if included(path))


def validate_fences(paths: list[Path]) -> tuple[list[str], list[str], list[str]]:
    fence_errors: list[str] = []
    python_errors: list[str] = []
    json_errors: list[str] = []

    for path in paths:
        active_marker: str | None = None
        language: str | None = None
        start_line = 0
        block: list[str] = []

        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            match = FENCE_PATTERN.match(line)
            if match:
                marker = match.group("marker")
                info = match.group("info").strip()
                if active_marker is None:
                    active_marker = marker
                    language = info.split(maxsplit=1)[0].lower() if info else ""
                    start_line = line_number
                    block = []
                elif (
                    marker[0] == active_marker[0]
                    and len(marker) >= len(active_marker)
                    and not info
                ):
                    source = "\n".join(block)
                    label = f"{path.relative_to(ROOT)}:{start_line}"
                    if language in {"python", "py"}:
                        try:
                            ast.parse(textwrap.dedent(source), filename=label)
                        except SyntaxError as error:
                            python_errors.append(f"{label}: {error.msg} at block line {error.lineno}")
                    elif language == "json":
                        try:
                            json.loads(source)
                        except json.JSONDecodeError as error:
                            json_errors.append(f"{label}: {error.msg} at block line {error.lineno}")
                    active_marker = None
                    language = None
                    start_line = 0
                    block = []
                else:
                    block.append(line)
                continue

            if active_marker is not None:
                block.append(line)

        if active_marker is not None:
            fence_errors.append(
                f"{path.relative_to(ROOT)}:{start_line}: unclosed {language or 'plain'} fence"
            )

    return fence_errors, python_errors, json_errors


def prose_without_fences(text: str) -> str:
    lines: list[str] = []
    active_marker: str | None = None
    for line in text.splitlines(keepends=True):
        match = FENCE_PATTERN.match(line.rstrip("\r\n"))
        if match:
            marker = match.group("marker")
            info = match.group("info").strip()
            if active_marker is None:
                active_marker = marker
            elif (
                marker[0] == active_marker[0]
                and len(marker) >= len(active_marker)
                and not info
            ):
                active_marker = None
            lines.append("\n")
        elif active_marker is not None:
            lines.append("\n")
        else:
            lines.append(line)
    return "".join(lines)


def resolve_wikilinks(paths: list[Path]) -> tuple[list[str], list[str]]:
    by_stem: dict[str, list[Path]] = defaultdict(list)
    repository_files = {
        path.resolve() for path in ROOT.rglob("*") if path.is_file() and included(path)
    }
    for path in paths:
        by_stem[path.stem].append(path)

    formal_missing: list[str] = []
    placeholder_missing: list[str] = []
    for path in paths:
        text = prose_without_fences(path.read_text(encoding="utf-8-sig"))
        for match in WIKILINK_PATTERN.finditer(text):
            raw = match.group(1)
            target = raw.split("|", 1)[0].split("#", 1)[0].strip()
            if not target:
                continue
            normalized = target.replace("/", "\\")
            target_path = Path(normalized)
            has_explicit_path = "/" in target or "\\" in target
            candidates = [ROOT / target_path, path.parent / target_path]
            resolved = False
            for candidate in candidates:
                variants = [candidate, Path(f"{candidate}.md")]
                if any(variant.resolve() in repository_files for variant in variants):
                    resolved = True
                    break
            leaf = normalized.rsplit("\\", 1)[-1]
            if leaf.lower().endswith(".md"):
                leaf = leaf[:-3]
            if not resolved and not has_explicit_path and leaf in by_stem:
                resolved = True
            if not resolved:
                line_number = text.count("\n", 0, match.start()) + 1
                item = f"{path.relative_to(ROOT)}:{line_number}: {target}"
                is_formal = (
                    "/" in target
                    or "\\" in target
                    or re.match(r"^(?:E\d{2}|P0\d|RQ\d{2}|GF\d{2})[-_ ]", target) is not None
                )
                if "模板" in path.parts:
                    is_formal = False
                if is_formal:
                    formal_missing.append(item)
                else:
                    placeholder_missing.append(item)
    return formal_missing, placeholder_missing


def validate_active_p03_contract(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        relative = path.relative_to(ROOT)
        if (
            "审计与整改" in relative.parts
            or "99_归档" in relative.parts
            or "artifacts" in relative.parts
        ):
            continue

        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            if LEGACY_RAG_ROUTE in line:
                is_explicit_legacy_example = (
                    relative in LEGACY_ROUTE_EXCEPTIONS
                    and ("同步基线" in line or "历史" in line or "旧版" in line)
                )
                if not is_explicit_legacy_example:
                    errors.append(
                        f"{relative}:{line_number}: stale P03 route {LEGACY_RAG_ROUTE}; "
                        "use POST /tasks with task_type=rag_retrieval"
                    )

            if STALE_P03_VERSION_PATTERN.search(line):
                errors.append(
                    f"{relative}:{line_number}: stale current P03 version; use P03 v0.3.1"
                )
    return errors


def main() -> int:
    global ROOT
    ROOT = parse_args().root.resolve()
    paths = markdown_files()
    fence_errors, python_errors, json_errors = validate_fences(paths)
    formal_missing_links, placeholder_missing_links = resolve_wikilinks(paths)
    active_contract_errors = validate_active_p03_contract(paths)
    report = {
        "markdown_files": len(paths),
        "fence_errors": fence_errors,
        "python_block_errors": python_errors,
        "json_block_errors": json_errors,
        "formal_missing_wikilinks_count": len(formal_missing_links),
        "formal_missing_wikilinks": formal_missing_links,
        "placeholder_wikilinks_count": len(placeholder_missing_links),
        "placeholder_wikilinks_sample": placeholder_missing_links[:25],
        "active_contract_errors": active_contract_errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if (
        fence_errors
        or python_errors
        or json_errors
        or formal_missing_links
        or active_contract_errors
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
