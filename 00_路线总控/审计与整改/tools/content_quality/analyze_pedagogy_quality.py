from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


TEXTBOOK_SUFFIXES = ("_适配教材.md", "_章节教材.md")
M05_SPLIT_INDEX = Path(
    "10_学习模块/M05_任务队列与调度/M05_任务队列与调度_章节教材.md"
)
M05_CHAPTER_DIRECTORY = Path("10_学习模块/M05_任务队列与调度/教材章节")
EXPECTED_ACTIVE_TEXTBOOKS = 22
EXPECTED_ARCHIVED_TEXTBOOKS = 1
EXPECTED_ACTIVE_CHAPTERS = 210
CHAPTER_TITLE_RE = re.compile(
    r"^第\s*(?:\d+(?:\.\d+)*(?:[A-Za-z])?|[一二三四五六七八九十百]+)\s*章(?:[：:\s]|$)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
HTML_IMAGE_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
HTML_ALT_RE = re.compile(r"\balt\s*=\s*(['\"]).*?\1", re.I)
TABLE_DELIMITER_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
CONTENT_TYPES = (
    "instructional",
    "workbook",
    "reference",
    "design-note",
    "solution",
    "appendix",
)
UNCLASSIFIED_CONTENT_TYPE = "unclassified"
CONTENT_TYPE_TOKEN_RE = r"[A-Za-z][A-Za-z0-9-]*"
CONTENT_MARKER_RE = re.compile(
    rf"<!--\s*textbook-content:\s*(default|type)\s*=\s*"
    rf"({CONTENT_TYPE_TOKEN_RE})\s*-->",
    re.I,
)
CONTENT_TYPE_QUOTE_RE = re.compile(
    rf"^\s*>\s*(?:内容类型|content[ -]?type)\s*[：:]\s*`?"
    rf"({CONTENT_TYPE_TOKEN_RE})`?(?:\s|$)",
    re.I,
)
DEFAULT_CONTENT_TYPE_QUOTE_RE = re.compile(
    rf"^\s*>\s*(?:默认内容类型|内容类型默认值|default\s+content[ -]?type)\s*"
    rf"[：:]\s*`?({CONTENT_TYPE_TOKEN_RE})`?(?:\s|$)",
    re.I,
)
TYPED_HEADING_CONTENT_TYPE_RE = re.compile(
    rf"(?:\[|\{{|\(|（)\s*(?:content[ -]?type|type)\s*[=:：]\s*`?"
    rf"({CONTENT_TYPE_TOKEN_RE})`?\s*(?:\]|\}}|\)|）)\s*$",
    re.I,
)
BARE_HEADING_CONTENT_TYPE_RE = re.compile(
    r"(?:\[|\(|（)\s*(" + "|".join(map(re.escape, CONTENT_TYPES))
    + r")\s*(?:\]|\)|）)\s*$",
    re.I,
)

ROLE_PATTERNS = {
    "objectives": re.compile(
        r"学习目标|本章目标|本节目标|本章解决什么问题|为什么要学|你将学会|"
        r"学完.*能够|应该.*掌握|真正要解决|想给你什么|项目目标|^目标$"
    ),
    "examples": re.compile(
        r"(?i:worked\s+example)|最小示例|代码示例|完整示例|示例|例子|案例|演示|样例|最小代码|最小流程|"
        r"贯通流程|逐行解释|从一个.*(?:场景|报错|问题).*开始|真实.*(?:场景|报错)"
    ),
    "counterexamples": re.compile(
        r"反例|坏例|坏味道|错误示例|错误做法|常见错误|踩坑|失败案例|失败模式"
    ),
    "practice": re.compile(
        r"小练习|练习|独立变式|观察实验|动手|实践任务|实验任务|课后任务|动手任务|巩固任务|"
        r"本章你要做什么|复盘问题|本章小实验|可判定练习"
    ),
    "acceptance": re.compile(
        r"本章检查标准|检查标准|学习检查|验收|完成标准|自测|检查清单|最终检查"
    ),
    "sources": re.compile(
        r"本章依据|本章来源|本节来源|资料来源|参考资料|推荐资料|推荐阅读|延伸阅读|官方文档|外部资料|来源映射"
        r"|权威资料|资料使用原则"
    ),
}


@dataclass(frozen=True)
class Heading:
    line: int
    level: int
    title: str


@dataclass(frozen=True)
class CodeFence:
    start_line: int
    end_line: int
    language: str
    content_line_count: int


@dataclass(frozen=True)
class ParsedMarkdown:
    lines: list[str]
    headings: list[Heading]
    fences: list[CodeFence]
    prose_line_numbers: set[int]
    unclosed_fence_start: int | None


@dataclass(frozen=True)
class ContentTypeCandidate:
    value: str
    source: str
    line: int


def parse_markdown(path: Path) -> ParsedMarkdown:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    headings: list[Heading] = []
    fences: list[CodeFence] = []
    prose_line_numbers: set[int] = set()
    active_marker: str | None = None
    active_language = ""
    active_start = 0

    for line_number, line in enumerate(lines, start=1):
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if active_marker is None:
                active_marker = marker
                info = fence.group(2).strip()
                active_language = info.split()[0].lower() if info else ""
                active_start = line_number
            elif (
                marker[0] == active_marker[0]
                and len(marker) >= len(active_marker)
                and not fence.group(2).strip()
            ):
                fences.append(
                    CodeFence(
                        start_line=active_start,
                        end_line=line_number,
                        language=active_language,
                        content_line_count=max(0, line_number - active_start - 1),
                    )
                )
                active_marker = None
                active_language = ""
                active_start = 0
            continue
        if active_marker is not None:
            continue
        prose_line_numbers.add(line_number)
        heading = HEADING_RE.match(line)
        if heading:
            headings.append(
                Heading(
                    line=line_number,
                    level=len(heading.group(1)),
                    title=heading.group(2).strip(),
                )
            )

    return ParsedMarkdown(
        lines=lines,
        headings=headings,
        fences=fences,
        prose_line_numbers=prose_line_numbers,
        unclosed_fence_start=active_start if active_marker is not None else None,
    )


def find_chapter_headings(headings: list[Heading]) -> tuple[list[Heading], str]:
    h2_chapters = [
        heading
        for heading in headings
        if heading.level == 2 and CHAPTER_TITLE_RE.search(heading.title)
    ]
    if h2_chapters:
        return h2_chapters, "h2"
    h1_chapters = [
        heading
        for heading in headings
        if heading.level == 1 and CHAPTER_TITLE_RE.search(heading.title)
    ]
    if h1_chapters:
        return h1_chapters, "h1_fallback"
    return [], "none"


def role_for_heading(title: str) -> list[str]:
    return [name for name, pattern in ROLE_PATTERNS.items() if pattern.search(title)]


def resolve_content_type(
    candidates: list[ContentTypeCandidate],
    fallback: ContentTypeCandidate | None = None,
) -> dict[str, object]:
    if not candidates:
        if fallback is not None:
            return {
                "content_type": fallback.value,
                "content_type_source": fallback.source,
                "content_type_marker_line": fallback.line,
                "content_type_issues": [],
            }
        return {
            "content_type": UNCLASSIFIED_CONTENT_TYPE,
            "content_type_source": UNCLASSIFIED_CONTENT_TYPE,
            "content_type_marker_line": None,
            "content_type_issues": [],
        }

    invalid = [candidate for candidate in candidates if candidate.value not in CONTENT_TYPES]
    if invalid:
        return {
            "content_type": UNCLASSIFIED_CONTENT_TYPE,
            "content_type_source": "invalid_marker",
            "content_type_marker_line": invalid[0].line,
            "content_type_issues": [
                {
                    "kind": "unknown_content_type",
                    "line": candidate.line,
                    "source": candidate.source,
                    "value": candidate.value,
                    "allowed_values": list(CONTENT_TYPES),
                }
                for candidate in invalid
            ],
        }

    distinct_values = sorted({candidate.value for candidate in candidates})
    if len(distinct_values) > 1:
        return {
            "content_type": UNCLASSIFIED_CONTENT_TYPE,
            "content_type_source": "conflicting_markers",
            "content_type_marker_line": candidates[0].line,
            "content_type_issues": [
                {
                    "kind": "conflicting_content_types",
                    "values": distinct_values,
                    "markers": [
                        {
                            "line": candidate.line,
                            "source": candidate.source,
                            "value": candidate.value,
                        }
                        for candidate in candidates
                    ],
                }
            ],
        }

    selected = candidates[0]
    return {
        "content_type": selected.value,
        "content_type_source": selected.source,
        "content_type_marker_line": selected.line,
        "content_type_issues": [],
    }


def content_type_candidates_in_lines(
    parsed: ParsedMarkdown,
    start_line: int,
    end_line: int,
    marker_key: str,
    marker_source: str,
    quote_pattern: re.Pattern[str] | None = None,
    quote_source: str | None = None,
) -> list[ContentTypeCandidate]:
    candidates: list[ContentTypeCandidate] = []
    for line_number in range(start_line, end_line + 1):
        if line_number not in parsed.prose_line_numbers:
            continue
        line = parsed.lines[line_number - 1]
        for match in CONTENT_MARKER_RE.finditer(line):
            if match.group(1).lower() != marker_key:
                continue
            candidates.append(
                ContentTypeCandidate(
                    value=match.group(2).lower(),
                    source=marker_source,
                    line=line_number,
                )
            )
        if quote_pattern is not None:
            quote = quote_pattern.match(line)
            if quote:
                candidates.append(
                    ContentTypeCandidate(
                        value=quote.group(1).lower(),
                        source=quote_source or marker_source,
                        line=line_number,
                    )
                )
    return candidates


def resolve_document_default(
    parsed: ParsedMarkdown,
    chapter_headings: list[Heading],
    inherited_default: ContentTypeCandidate | None = None,
) -> dict[str, object]:
    preamble_end = (
        min(heading.line for heading in chapter_headings) - 1
        if chapter_headings
        else len(parsed.lines)
    )
    candidates = content_type_candidates_in_lines(
        parsed,
        1,
        preamble_end,
        marker_key="default",
        marker_source="document_default_marker",
        quote_pattern=DEFAULT_CONTENT_TYPE_QUOTE_RE,
        quote_source="document_default_quote",
    )
    candidates.extend(
        content_type_candidates_in_lines(
            parsed,
            1,
            preamble_end,
            marker_key="__quote_only__",
            marker_source="document_content_type_quote",
            quote_pattern=CONTENT_TYPE_QUOTE_RE,
            quote_source="document_content_type_quote",
        )
    )
    return resolve_content_type(candidates, inherited_default)


def resolve_chapter_content_type(
    parsed: ParsedMarkdown,
    chapter_heading: Heading,
    prefix_end_line: int,
    document_default: dict[str, object],
) -> dict[str, object]:
    candidates = content_type_candidates_in_lines(
        parsed,
        chapter_heading.line + 1,
        prefix_end_line,
        marker_key="type",
        marker_source="chapter_marker",
        quote_pattern=CONTENT_TYPE_QUOTE_RE,
        quote_source="chapter_quote",
    )
    typed_heading = TYPED_HEADING_CONTENT_TYPE_RE.search(chapter_heading.title)
    bare_heading = BARE_HEADING_CONTENT_TYPE_RE.search(chapter_heading.title)
    heading_match = typed_heading or bare_heading
    if heading_match:
        candidates.insert(
            0,
            ContentTypeCandidate(
                value=heading_match.group(1).lower(),
                source="chapter_heading_tag",
                line=chapter_heading.line,
            ),
        )

    fallback = None
    if document_default["content_type"] != UNCLASSIFIED_CONTENT_TYPE:
        fallback = ContentTypeCandidate(
            value=str(document_default["content_type"]),
            source=str(document_default["content_type_source"]),
            line=int(document_default["content_type_marker_line"] or 0),
        )
    return resolve_content_type(candidates, fallback)


def line_range_text(parsed: ParsedMarkdown, start_line: int, end_line: int) -> str:
    return "\n".join(
        parsed.lines[line_number - 1]
        for line_number in range(start_line, end_line + 1)
        if line_number in parsed.prose_line_numbers
    )


def section_end_line(
    headings: list[Heading],
    heading_index: int,
    maximum_end_line: int,
) -> int:
    heading = headings[heading_index]
    for following in headings[heading_index + 1 :]:
        if following.line > maximum_end_line:
            break
        if following.level <= heading.level:
            return following.line - 1
    return maximum_end_line


def count_tables(parsed: ParsedMarkdown, start_line: int, end_line: int) -> int:
    return sum(
        bool(TABLE_DELIMITER_RE.match(parsed.lines[line_number - 1]))
        for line_number in range(start_line, end_line + 1)
        if line_number in parsed.prose_line_numbers
    )


def visual_evidence(parsed: ParsedMarkdown, start_line: int, end_line: int) -> dict[str, int]:
    prose_text = line_range_text(parsed, start_line, end_line)
    fences = [
        fence
        for fence in parsed.fences
        if start_line <= fence.start_line <= end_line
    ]
    mermaid_fences = [fence for fence in fences if fence.language == "mermaid"]
    mermaid_accessible_count = 0
    for fence in mermaid_fences:
        content = "\n".join(parsed.lines[fence.start_line : fence.end_line - 1])
        has_title = bool(re.search(r"^\s*accTitle\s*:\s*\S", content, re.M))
        has_description = bool(re.search(r"^\s*accDescr\s*:\s*\S", content, re.M))
        mermaid_accessible_count += has_title and has_description
    mermaid_count = len(mermaid_fences)
    markdown_image_alts = MARKDOWN_IMAGE_RE.findall(prose_text)
    markdown_image_count = len(markdown_image_alts)
    markdown_images_missing_alt = sum(not alt.strip() for alt in markdown_image_alts)
    html_image_tags = HTML_IMAGE_TAG_RE.findall(prose_text)
    html_image_count = len(html_image_tags)
    html_images_missing_alt = sum(not HTML_ALT_RE.search(tag) for tag in html_image_tags)
    table_count = count_tables(parsed, start_line, end_line)
    return {
        "table_count": table_count,
        "markdown_image_count": markdown_image_count,
        "markdown_images_missing_alt": markdown_images_missing_alt,
        "html_image_count": html_image_count,
        "html_images_missing_alt": html_images_missing_alt,
        "mermaid_count": mermaid_count,
        "mermaid_accessible_count": mermaid_accessible_count,
        "mermaid_missing_accessibility_count": (
            mermaid_count - mermaid_accessible_count
        ),
        "visual_item_count": table_count + markdown_image_count + html_image_count + mermaid_count,
    }


def analyze_chapter(
    parsed: ParsedMarkdown,
    chapter_heading: Heading,
    end_line: int,
    document_default: dict[str, object],
) -> dict[str, object]:
    chapter_headings = [
        heading
        for heading in parsed.headings
        if chapter_heading.line <= heading.line <= end_line
    ]
    role_rows: dict[str, dict[str, object]] = {}
    for role in ROLE_PATTERNS:
        matching_indexes = [
            index
            for index, heading in enumerate(chapter_headings)
            if role in role_for_heading(heading.title)
        ]
        evidence = []
        total_characters = 0
        role_code_fences = 0
        for index in matching_indexes:
            heading = chapter_headings[index]
            section_end = section_end_line(chapter_headings, index, end_line)
            section_text = line_range_text(parsed, heading.line + 1, section_end)
            section_fences = [
                fence
                for fence in parsed.fences
                if heading.line < fence.start_line <= section_end
            ]
            total_characters += len(re.sub(r"\s+", "", section_text))
            role_code_fences += len(section_fences)
            evidence.append(
                {
                    "heading": heading.title,
                    "heading_line": heading.line,
                    "end_line": section_end,
                    "prose_character_count": len(re.sub(r"\s+", "", section_text)),
                    "code_fence_count": len(section_fences),
                }
            )
        role_rows[role] = {
            "explicit_section_present": bool(evidence),
            "section_count": len(evidence),
            "prose_character_count": total_characters,
            "code_fence_count": role_code_fences,
            "evidence": evidence,
        }

    chapter_text = line_range_text(parsed, chapter_heading.line, end_line)
    chapter_fences = [
        fence
        for fence in parsed.fences
        if chapter_heading.line <= fence.start_line <= end_line
    ]
    language_counts = Counter(fence.language or "<none>" for fence in chapter_fences)
    external_urls = sorted(set(URL_RE.findall(chapter_text)))
    wiki_links = sorted(set(WIKILINK_RE.findall(chapter_text)))
    visual = visual_evidence(parsed, chapter_heading.line, end_line)
    missing_roles = [
        role
        for role, row in role_rows.items()
        if not row["explicit_section_present"]
    ]
    prefix_end_line = (
        chapter_headings[1].line - 1 if len(chapter_headings) > 1 else end_line
    )
    content_type = resolve_chapter_content_type(
        parsed,
        chapter_heading,
        prefix_end_line,
        document_default,
    )
    return {
        "title": chapter_heading.title,
        "heading_level": chapter_heading.level,
        "start_line": chapter_heading.line,
        "end_line": end_line,
        "line_count": end_line - chapter_heading.line + 1,
        "prose_character_count": len(re.sub(r"\s+", "", chapter_text)),
        "heading_count": len(chapter_headings),
        "code_fence_count": len(chapter_fences),
        "code_fence_language_counts": dict(language_counts.most_common()),
        "external_url_count": len(external_urls),
        "external_urls": external_urls,
        "wiki_link_count": len(wiki_links),
        "wiki_links": wiki_links,
        "roles": role_rows,
        "missing_explicit_role_sections": missing_roles,
        "visual_evidence": visual,
        **content_type,
    }


def analyze_document(
    path: Path,
    root: Path,
    inherited_default: ContentTypeCandidate | None = None,
) -> dict[str, object]:
    parsed = parse_markdown(path)
    chapter_headings, chapter_mode = find_chapter_headings(parsed.headings)
    document_default = resolve_document_default(
        parsed,
        chapter_headings,
        inherited_default,
    )
    chapters = []
    for heading in chapter_headings:
        heading_index = parsed.headings.index(heading)
        end_line = section_end_line(parsed.headings, heading_index, len(parsed.lines))
        chapters.append(analyze_chapter(parsed, heading, end_line, document_default))

    chapter_line_numbers = {
        heading.line
        for heading in chapter_headings
    }
    outside_chapter_role_headings = []
    for heading in parsed.headings:
        roles = role_for_heading(heading.title)
        if not roles or heading.line in chapter_line_numbers:
            continue
        if any(
            chapter["start_line"] <= heading.line <= chapter["end_line"]
            for chapter in chapters
        ):
            continue
        outside_chapter_role_headings.append(
            {"heading": heading.title, "line": heading.line, "roles": roles}
        )

    all_text = line_range_text(parsed, 1, len(parsed.lines))
    all_fence_languages = Counter(fence.language or "<none>" for fence in parsed.fences)
    return {
        "file": str(path.relative_to(root)),
        "status": "archived" if "99_归档" in path.parts else "active",
        "chapter_detection_mode": chapter_mode,
        "line_count": len(parsed.lines),
        "heading_count": len(parsed.headings),
        "chapter_count": len(chapters),
        "code_fence_count": len(parsed.fences),
        "code_fence_language_counts": dict(all_fence_languages.most_common()),
        "unclosed_fence_start_line": parsed.unclosed_fence_start,
        "external_url_count": len(set(URL_RE.findall(all_text))),
        "visual_evidence": visual_evidence(parsed, 1, len(parsed.lines)),
        "outside_chapter_role_headings": outside_chapter_role_headings,
        "default_content_type": document_default["content_type"],
        "default_content_type_source": document_default["content_type_source"],
        "default_content_type_marker_line": document_default[
            "content_type_marker_line"
        ],
        "content_type_issues": document_default["content_type_issues"],
        "content_type_counts": dict(
            Counter(str(chapter["content_type"]) for chapter in chapters)
        ),
        "chapters": chapters,
    }


def analyze_split_textbook(
    index_path: Path,
    chapter_paths: list[Path],
    root: Path,
) -> dict[str, object]:
    index = analyze_document(index_path, root)
    inherited_default = None
    if index["default_content_type"] != UNCLASSIFIED_CONTENT_TYPE:
        inherited_default = ContentTypeCandidate(
            value=str(index["default_content_type"]),
            source="split_index_default",
            line=int(index["default_content_type_marker_line"] or 0),
        )
    chapter_documents = [
        analyze_document(path, root, inherited_default) for path in chapter_paths
    ]
    chapters: list[dict[str, object]] = []
    for path, document in zip(chapter_paths, chapter_documents, strict=True):
        if document["chapter_count"] != 1:
            raise ValueError(f"Split M05 chapter must contain one chapter heading: {path}")
        chapter = document["chapters"][0]
        chapter["source_file"] = str(path.relative_to(root))
        chapters.append(chapter)

    visual_keys = index["visual_evidence"].keys()
    combined_visual = {
        key: int(index["visual_evidence"][key])
        + sum(int(document["visual_evidence"][key]) for document in chapter_documents)
        for key in visual_keys
    }
    languages = Counter(index["code_fence_language_counts"])
    for document in chapter_documents:
        languages.update(document["code_fence_language_counts"])

    index.update(
        {
            "chapter_detection_mode": "split_h1",
            "line_count": int(index["line_count"])
            + sum(int(document["line_count"]) for document in chapter_documents),
            "heading_count": int(index["heading_count"])
            + sum(int(document["heading_count"]) for document in chapter_documents),
            "chapter_count": len(chapters),
            "code_fence_count": int(index["code_fence_count"])
            + sum(int(document["code_fence_count"]) for document in chapter_documents),
            "code_fence_language_counts": dict(languages.most_common()),
            "unclosed_fence_start_line": (
                1
                if any(
                    document["unclosed_fence_start_line"] is not None
                    for document in chapter_documents
                )
                else index["unclosed_fence_start_line"]
            ),
            "external_url_count": int(index["external_url_count"])
            + sum(int(document["external_url_count"]) for document in chapter_documents),
            "visual_evidence": combined_visual,
            "split_chapter_files": [str(path.relative_to(root)) for path in chapter_paths],
            "content_type_counts": dict(
                Counter(str(chapter["content_type"]) for chapter in chapters)
            ),
            "chapters": chapters,
        }
    )
    return index


def calculate_role_coverage(
    chapters: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    coverage: dict[str, dict[str, object]] = {}
    for role in ROLE_PATTERNS:
        present = sum(
            bool(chapter["roles"][role]["explicit_section_present"])
            for chapter in chapters
        )
        coverage[role] = {
            "chapter_count": len(chapters),
            "chapters_with_explicit_section": present,
            "chapters_without_explicit_section": len(chapters) - present,
            "coverage_ratio": round(present / len(chapters), 4)
            if chapters
            else None,
        }
    return coverage


def build_summary(documents: list[dict[str, object]]) -> dict[str, object]:
    active_documents = [row for row in documents if row["status"] == "active"]
    archived_documents = [row for row in documents if row["status"] == "archived"]
    active_chapters = [
        chapter
        for document in active_documents
        for chapter in document["chapters"]
    ]
    content_type_counts = Counter(
        str(chapter["content_type"]) for chapter in active_chapters
    )
    instructional_chapters = [
        chapter
        for chapter in active_chapters
        if chapter["content_type"] == "instructional"
    ]
    content_type_issues = []
    for document in active_documents:
        for issue in document["content_type_issues"]:
            content_type_issues.append(
                {
                    "file": document["file"],
                    "scope": "document_default",
                    "issue": issue,
                }
            )
        for chapter in document["chapters"]:
            for issue in chapter["content_type_issues"]:
                content_type_issues.append(
                    {
                        "file": chapter.get("source_file", document["file"]),
                        "scope": "chapter",
                        "chapter": chapter["title"],
                        "issue": issue,
                    }
                )
    content_type_order = (*CONTENT_TYPES, UNCLASSIFIED_CONTENT_TYPE)
    role_coverage_by_content_type = {
        content_type: calculate_role_coverage(
            [
                chapter
                for chapter in active_chapters
                if chapter["content_type"] == content_type
            ]
        )
        for content_type in content_type_order
    }
    chapter_modes = Counter(document["chapter_detection_mode"] for document in active_documents)
    active_visuals = [document["visual_evidence"] for document in active_documents]
    unclosed_fence_documents = [
        document["file"]
        for document in documents
        if document["unclosed_fence_start_line"] is not None
    ]
    chapterless_active_documents = [
        document["file"]
        for document in active_documents
        if document["chapter_detection_mode"] == "none"
    ]
    scope_matches = (
        len(active_documents) == EXPECTED_ACTIVE_TEXTBOOKS
        and len(archived_documents) == EXPECTED_ARCHIVED_TEXTBOOKS
        and len(active_chapters) == EXPECTED_ACTIVE_CHAPTERS
        and not unclosed_fence_documents
        and not chapterless_active_documents
    )
    return {
        "active_textbook_count": len(active_documents),
        "archived_textbook_count": len(archived_documents),
        "active_chapter_count": len(active_chapters),
        "active_content_type_counts": {
            content_type: content_type_counts[content_type]
            for content_type in content_type_order
        },
        "active_classified_chapter_count": sum(
            content_type_counts[content_type] for content_type in CONTENT_TYPES
        ),
        "active_unclassified_chapter_count": content_type_counts[
            UNCLASSIFIED_CONTENT_TYPE
        ],
        "active_instructional_chapter_count": len(instructional_chapters),
        "active_content_type_issue_count": len(content_type_issues),
        "active_content_type_issues": content_type_issues,
        "active_chapter_detection_modes": dict(chapter_modes.most_common()),
        "active_code_fence_count": sum(int(row["code_fence_count"]) for row in active_documents),
        "active_visual_item_count": sum(
            int(row["visual_evidence"]["visual_item_count"])
            for row in active_documents
        ),
        "active_accessibility": {
            "markdown_image_count": sum(
                int(row["markdown_image_count"]) for row in active_visuals
            ),
            "markdown_images_missing_alt": sum(
                int(row["markdown_images_missing_alt"]) for row in active_visuals
            ),
            "html_image_count": sum(
                int(row["html_image_count"]) for row in active_visuals
            ),
            "html_images_missing_alt": sum(
                int(row["html_images_missing_alt"]) for row in active_visuals
            ),
            "mermaid_count": sum(int(row["mermaid_count"]) for row in active_visuals),
            "mermaid_accessible_count": sum(
                int(row["mermaid_accessible_count"]) for row in active_visuals
            ),
        },
        "role_coverage": calculate_role_coverage(instructional_chapters),
        "role_coverage_scope": (
            "Explicitly classified instructional chapters only. Unclassified and non-instructional "
            "chapters are excluded from this denominator."
        ),
        "role_coverage_by_content_type": role_coverage_by_content_type,
        "all_active_role_coverage": calculate_role_coverage(active_chapters),
        "scope_expectation": {
            "expected_active_textbooks": EXPECTED_ACTIVE_TEXTBOOKS,
            "expected_archived_textbooks": EXPECTED_ARCHIVED_TEXTBOOKS,
            "expected_active_chapters": EXPECTED_ACTIVE_CHAPTERS,
            "chapterless_active_documents": chapterless_active_documents,
            "unclosed_fence_documents": unclosed_fence_documents,
            "matches_expectation": scope_matches,
        },
        "interpretation": (
            "Role coverage means an explicit role-labelled section was found inside the same chapter. "
            "The primary role_coverage denominator contains only explicitly classified instructional "
            "chapters; all_active_role_coverage preserves the earlier whole-scope view. A missing "
            "section is a review candidate, not proof that the concept is absent from prose."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    textbook_root = root / "10_学习模块"
    paths = sorted(
        path
        for path in textbook_root.rglob("*.md")
        if path.name.endswith(TEXTBOOK_SUFFIXES)
    )
    documents = []
    for path in paths:
        if path.relative_to(root) == M05_SPLIT_INDEX:
            chapter_root = root / M05_CHAPTER_DIRECTORY
            chapter_paths = sorted(chapter_root.glob("*.md"))
            if len(chapter_paths) != 13:
                raise ValueError(
                    f"Expected 13 split M05 chapters, found {len(chapter_paths)}"
                )
            documents.append(analyze_split_textbook(path, chapter_paths, root))
        else:
            documents.append(analyze_document(path, root))
    report = {
        "schema_version": "1.3",
        "method": {
            "chapter_boundary": (
                "Use anchored H2 '第 X 章' headings with Arabic numerals, an optional inserted "
                "letter suffix such as 6A, or Chinese numerals; only fall back to anchored H1 "
                "chapters when a textbook has no matching H2 chapter. M05 split chapter files "
                "are aggregated under their stable compatibility index."
            ),
            "role_detection": (
                "Match section headings within each chapter. Whole-file keyword presence is not "
                "used to claim chapter coverage."
            ),
            "content_type_detection": (
                "Use explicit textbook-content HTML comments, supported heading tags, or content "
                "type quote metadata. Chapter markers override a document default. Missing, "
                "unknown, or conflicting explicit types remain unclassified; titles and prose "
                "keywords are not used to guess a type."
            ),
            "primary_role_coverage_scope": "Explicitly classified instructional chapters only.",
            "code_fence_awareness": True,
            "archive_detection": "Any textbook below a 99_归档 path is archived.",
        },
        "summary": build_summary(documents),
        "documents": documents,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["scope_expectation"]["matches_expectation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
