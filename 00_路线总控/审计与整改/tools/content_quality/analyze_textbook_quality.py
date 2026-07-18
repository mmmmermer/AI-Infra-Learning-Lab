from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


EXCLUDED_PARTS = {
    ".git",
    ".tools",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
TEXTBOOK_SUFFIXES = ("_适配教材.md", "_章节教材.md")
M05_SPLIT_INDEX = Path(
    "10_学习模块/M05_任务队列与调度/M05_任务队列与调度_章节教材.md"
)
M05_CHAPTER_DIRECTORY = Path("10_学习模块/M05_任务队列与调度/教材章节")
FEATURE_PATTERNS = {
    "objectives": re.compile(r"学习目标|本章目标|你将学会|学习结果"),
    "prerequisites": re.compile(r"前置|先修|开始前|环境准备"),
    "concepts": re.compile(r"核心概念|关键概念|概念解释|基本概念"),
    "examples": re.compile(r"最小示例|代码示例|示例|例子"),
    "practice": re.compile(r"练习|实验|动手|任务"),
    "acceptance": re.compile(r"验收|检查标准|完成标准|自测|检查清单"),
    "sources": re.compile(r"参考资料|资料来源|官方文档|延伸阅读|来源"),
    "boundaries": re.compile(r"边界|局限|不做|不能|不得|适用范围"),
}
PLACEHOLDER_PATTERN = re.compile(r"\bTODO\b|\bTBD\b|待补充|待完善|内容占位")
STALE_PYTHON_PATTERN = re.compile(r"Python\s*3\.(8|9)(?!\d)", re.IGNORECASE)
EXPLANATORY_PATTERN = re.compile(r"历史|旧|过期|EOL|不再|停止支持|不能|不得|废弃|审计")
URL_PATTERN = re.compile(r"https?://[^\s)>\]]+")
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def is_excluded(path: Path, root: Path, output_dir: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True
    if "教材内容质量大检查报告" in path.name:
        return True
    try:
        path.relative_to(output_dir)
        return True
    except ValueError:
        return False


def prose_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    active_fence: str | None = None
    in_front_matter = False

    def flush() -> None:
        if not current:
            return
        paragraph = " ".join(item.strip() for item in current).strip()
        current.clear()
        if len(paragraph) < 100:
            return
        if paragraph.startswith(("#", "- ", "* ", ">", "|", "[[")):
            return
        normalized = re.sub(r"\s+", "", paragraph)
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}", "<DATE>", normalized)
        if len(normalized) >= 100:
            paragraphs.append(normalized)

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if line_number == 1 and stripped == "---":
            in_front_matter = True
            continue
        if in_front_matter:
            if stripped == "---":
                in_front_matter = False
            continue
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            flush()
            marker = fence_match.group(1)
            if active_fence is None:
                active_fence = marker
            elif marker[0] == active_fence[0] and len(marker) >= len(active_fence):
                active_fence = None
            continue
        if active_fence is not None:
            continue
        if not stripped:
            flush()
            continue
        if re.match(r"^\s*(#|[-*+] |\d+\. |> |\|)", line):
            flush()
            continue
        current.append(line)
    flush()
    return paragraphs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_files = [
        path
        for path in root.rglob("*.md")
        if not is_excluded(path, root, output_dir)
    ]
    area_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    textbooks: list[dict[str, object]] = []
    placeholders: list[dict[str, object]] = []
    stale_python: list[dict[str, object]] = []
    oversized_files: list[dict[str, object]] = []
    missing_fence_languages: list[dict[str, object]] = []
    duplicate_index: dict[str, list[str]] = defaultdict(list)
    total_urls = 0

    for path in markdown_files:
        relative = str(path.relative_to(root))
        area = Path(relative).parts[0]
        area_counts[area] += 1
        text = path.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        urls = sorted(set(URL_PATTERN.findall(text)))
        total_urls += len(urls)
        for url in urls:
            domain = urlparse(url.rstrip(".,;，。；")).netloc.lower()
            if domain:
                domain_counts[domain] += 1

        if len(lines) > 2_000:
            oversized_files.append(
                {"file": relative, "line_count": len(lines), "character_count": len(text)}
            )

        active_fence: str | None = None
        for line_number, line in enumerate(lines, start=1):
            fence_match = FENCE_PATTERN.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if active_fence is None:
                    if not fence_match.group(2).strip():
                        missing_fence_languages.append({"file": relative, "line": line_number})
                    active_fence = marker
                elif marker[0] == active_fence[0] and len(marker) >= len(active_fence):
                    active_fence = None
                continue
            if active_fence is None:
                for match in PLACEHOLDER_PATTERN.finditer(line):
                    placeholders.append(
                        {
                            "file": relative,
                            "line": line_number,
                            "match": match.group(0),
                            "text": line.strip()[:240],
                        }
                    )
                for match in STALE_PYTHON_PATTERN.finditer(line):
                    stale_python.append(
                        {
                            "file": relative,
                            "line": line_number,
                            "match": match.group(0),
                            "likely_explanatory": bool(EXPLANATORY_PATTERN.search(line)),
                            "text": line.strip()[:240],
                        }
                    )

        if area == "10_学习模块" and path.name.endswith(TEXTBOOK_SUFFIXES):
            textbook_text = text
            textbook_lines = lines
            textbook_urls = urls
            split_chapter_file_count = 0
            if path.relative_to(root) == M05_SPLIT_INDEX:
                chapter_paths = sorted((root / M05_CHAPTER_DIRECTORY).glob("*.md"))
                if len(chapter_paths) != 13:
                    raise ValueError(
                        f"Expected 13 split M05 chapters, found {len(chapter_paths)}"
                    )
                chapter_texts = [
                    chapter_path.read_text(encoding="utf-8-sig")
                    for chapter_path in chapter_paths
                ]
                textbook_text = text + "\n" + "\n".join(chapter_texts)
                textbook_lines = textbook_text.splitlines()
                textbook_urls = sorted(set(URL_PATTERN.findall(textbook_text)))
                split_chapter_file_count = len(chapter_paths)

            features = {
                name: bool(pattern.search(textbook_text))
                for name, pattern in FEATURE_PATTERNS.items()
            }
            textbooks.append(
                {
                    "file": relative,
                    "status": "archived" if "99_归档" in path.parts else "active",
                    "line_count": len(textbook_lines),
                    "heading_count": sum(
                        line.startswith("#") for line in textbook_lines
                    ),
                    "code_fence_pairs": sum(
                        bool(FENCE_PATTERN.match(line)) for line in textbook_lines
                    )
                    // 2,
                    "external_url_count": len(textbook_urls),
                    "split_chapter_file_count": split_chapter_file_count,
                    "features": features,
                    "missing_features": [name for name, present in features.items() if not present],
                }
            )

        for paragraph in prose_paragraphs(text):
            digest = hashlib.sha256(paragraph.encode("utf-8")).hexdigest()
            duplicate_index[digest].append(relative)

    duplicate_paragraphs = []
    for digest, files in duplicate_index.items():
        unique_files = sorted(set(files))
        if len(unique_files) >= 2:
            duplicate_paragraphs.append(
                {"sha256": digest, "file_count": len(unique_files), "files": unique_files}
            )
    duplicate_paragraphs.sort(key=lambda row: (-int(row["file_count"]), str(row["sha256"])))

    report = {
        "schema_version": "1.1",
        "markdown_file_count": len(markdown_files),
        "area_counts": dict(area_counts.most_common()),
        "textbook_file_count": len(textbooks),
        "active_textbook_file_count": sum(row["status"] == "active" for row in textbooks),
        "archived_textbook_file_count": sum(
            row["status"] == "archived" for row in textbooks
        ),
        "textbooks": sorted(textbooks, key=lambda row: str(row["file"])),
        "textbooks_missing_any_feature": sum(
            bool(row["missing_features"]) for row in textbooks
        ),
        "textbooks_without_external_urls": sum(
            row["external_url_count"] == 0 for row in textbooks
        ),
        "active_textbooks_missing_any_feature": sum(
            row["status"] == "active" and bool(row["missing_features"])
            for row in textbooks
        ),
        "active_textbooks_without_external_urls": sum(
            row["status"] == "active" and row["external_url_count"] == 0
            for row in textbooks
        ),
        "unique_external_url_occurrences": total_urls,
        "top_external_domains": dict(domain_counts.most_common(30)),
        "placeholder_count": len(placeholders),
        "placeholders": placeholders,
        "stale_python_reference_count": len(stale_python),
        "stale_python_non_explanatory_count": sum(
            not row["likely_explanatory"] for row in stale_python
        ),
        "stale_python_references": stale_python,
        "missing_fence_language_count": len(missing_fence_languages),
        "missing_fence_languages": missing_fence_languages,
        "oversized_file_count": len(oversized_files),
        "oversized_files": sorted(
            oversized_files, key=lambda row: -int(row["line_count"])
        ),
        "duplicate_paragraph_group_count": len(duplicate_paragraphs),
        "duplicate_paragraph_groups": duplicate_paragraphs[:100],
    }
    (output_dir / "custom_analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if not isinstance(value, list)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
