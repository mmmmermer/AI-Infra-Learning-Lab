from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from analyze_pedagogy_quality import parse_markdown


ENTRY_PATTERNS = {
    "audience": re.compile(r"目标读者|读者对象|适用人群|受众|适合.{0,20}(?:学习者|读者|工程师)"),
    "prerequisites": re.compile(r"前置|先修|开始之前|准备工作|环境检查|你需要"),
    "scope": re.compile(r"学习边界|适用范围|范围说明|第一轮|暂不|不包含|不展开|不能据此"),
    "version": re.compile(
        r"版本(?:基线|说明|要求|范围|边界)|兼容(?:性|版本)|Python\s+3\.\d+|Kubernetes\s+v?\d+\.\d+",
        re.I,
    ),
    "estimated_time": re.compile(r"预计(?:学习)?时间|建议用时|约\s*\d+(?:\.\d+)?\s*(?:分钟|小时|h\b)"),
    "outputs": re.compile(r"学习产物|交付物|最终产物|你将完成|产出"),
    "completion": re.compile(r"完成标准|完成口径|检查标准|学习检查|验收"),
    "navigation": re.compile(r"学习顺序|学习路径|核心路径|主线|选修|推荐顺序"),
    "content_type": re.compile(r"textbook-content:\s*(?:default|type)\s*="),
}

CHAPTER_HEADING_PATTERNS = {
    "context": re.compile(r"概述|背景|为什么|问题场景|真实场景|本章解决什么问题|先看一个问题"),
    "prerequisites": re.compile(r"前置|先修|开始之前|准备工作|环境检查|你需要"),
    "procedure": re.compile(r"步骤|操作|动手|实现流程|实验流程|实践任务|练习"),
    "expected_result": re.compile(r"预期(?:结果|输出|现象)|成功判据|检查标准|验证标准|完成标准|验收"),
    "troubleshooting": re.compile(r"故障排查|排错|诊断|失败(?:现象|处理|恢复|模式)|常见错误|修复|回归检查|踩坑"),
    "cleanup": re.compile(r"清理|回滚|删除(?:资源|环境)|恢复环境|善后"),
    "summary": re.compile(r"小结|总结|回顾|要点|本章结论|记住"),
    "next_steps": re.compile(r"下一步|后续|延伸阅读|拓展阅读|继续学习|相关内容"),
}

NUMBERED_STEP_RE = re.compile(r"^\s*(?:\d+[.)\u3001]|[a-zA-Z][.)])\s+\S")
STATEFUL_RE = re.compile(
    r"\b(?:kubectl|docker(?:\s+compose)?|kind|helm|redis-cli|psql|sqlite3)\b|"
    r"CREATE\s+TABLE|DROP\s+TABLE|启动服务|创建集群|写入数据库",
    re.I,
)
REFERENCE_TITLE_RE = re.compile(r"索引|参考|字段|接口|契约|速查|资料")
DESIGN_TITLE_RE = re.compile(r"设计|目标架构|规划|迁移|路线|展望|未来")
WORKBOOK_TITLE_RE = re.compile(r"实验|练习|实战|动手")

SOURCE_RULES = [
    {
        "id": "MS-LEARN-CONTENT-TYPES",
        "url": "https://learn.microsoft.com/en-us/training/support/learn-content-types",
        "use": "模块、单元、知识检查、互动练习和短时自包含课程的组织参照",
    },
    {
        "id": "MS-LEARN-MODULE-EXAMPLE",
        "url": "https://learn.microsoft.com/en-us/training/modules/fundamentals-generative-ai/",
        "use": "目标、先决条件、概念、练习、评估和总结的官方发布实例；不是普适强制模板",
    },
    {
        "id": "GOOGLE-TECH-WRITING-ONE",
        "url": "https://developers.google.com/tech-writing/one",
        "use": "受众、学习目标、硬件和网络条件以及可选内容的课程入口参照",
    },
    {
        "id": "GOOGLE-AUDIENCE",
        "url": "https://developers.google.com/tech-writing/one/audience",
        "use": "目标受众、已有知识和任务所需知识之间的差距",
    },
    {
        "id": "GOOGLE-DOCUMENTS",
        "url": "https://developers.google.com/tech-writing/one/documents",
        "use": "scope、non-scope、受众、前置知识和信息顺序",
    },
    {
        "id": "GOOGLE-SAMPLE-CODE",
        "url": "https://developers.google.com/tech-writing/two/sample-code",
        "use": "可构建、可运行、安全、持续测试且说明设置与预期结果的示例",
    },
    {
        "id": "GOOGLE-PROCEDURES",
        "url": "https://developers.google.com/style/procedures",
        "use": "过程型内容的上下文、编号步骤、单步动作和结果说明",
    },
    {
        "id": "GOOGLE-CODE-SAMPLES",
        "url": "https://developers.google.com/style/code-samples",
        "use": "示例代码的可读性、聚焦性、说明和可复制性",
    },
    {
        "id": "K8S-PAGE-TYPES",
        "url": "https://kubernetes.io/docs/contribute/style/page-content-types/",
        "use": "concept、task、tutorial、reference 的用途与建议章节结构",
    },
    {
        "id": "K8S-STYLE-GUIDE",
        "url": "https://kubernetes.io/docs/contribute/style/style-guide/",
        "use": "命令与输出、占位符、版本前置、危险提示和标题层级",
    },
    {
        "id": "K8S-CONTENT-GUIDE",
        "url": "https://kubernetes.io/docs/contribute/style/content-guide/",
        "use": "优先链接 canonical source，减少双份内容的维护漂移",
    },
    {
        "id": "PYTHON-DOC-TYPES",
        "url": "https://docs.python.org/3/",
        "use": "tutorial、HOWTO、library reference、language reference 的用途分离",
    },
    {
        "id": "PYTHON-TUTORIAL",
        "url": "https://docs.python.org/3/tutorial/",
        "use": "明确受众边界的非正式导入和自包含示例",
    },
    {
        "id": "PYTHON-HOWTO",
        "url": "https://docs.python.org/3/howto/",
        "use": "针对特定主题的深入说明",
    },
    {
        "id": "PYTHON-LANGUAGE-REFERENCE",
        "url": "https://docs.python.org/3/reference/",
        "use": "简洁、精确、尽量完整的语义参考，与教程分工",
    },
    {
        "id": "PYTHON-LIBRARY-REFERENCE",
        "url": "https://docs.python.org/3/library/",
        "use": "库与接口参考，不承担语言导学职责",
    },
    {
        "id": "GITHUB-DOC-FUNDAMENTALS",
        "url": "https://docs.github.com/en/contributing/writing-for-github-docs/about-githubs-documentation-fundamentals",
        "use": "准确、可访问、包容和一致的发布底线",
    },
    {
        "id": "GITHUB-DOC-BEST-PRACTICES",
        "url": "https://docs.github.com/en/contributing/writing-for-github-docs/best-practices-for-github-docs",
        "use": "受众、核心目的、内容类型、逻辑顺序和可扫描性",
    },
    {
        "id": "GITHUB-TUTORIAL",
        "url": "https://docs.github.com/en/contributing/style-guide-and-content-model/tutorial-content-type",
        "use": "教程的受众、前置、成果、完整流程、常见问题、结论和后续步骤",
    },
    {
        "id": "GITHUB-HOW-TO",
        "url": "https://docs.github.com/en/contributing/style-guide-and-content-model/how-to-content-type",
        "use": "单一任务、编号步骤、预期结果和已知痛点",
    },
    {
        "id": "GITHUB-TROUBLESHOOTING",
        "url": "https://docs.github.com/en/contributing/style-guide-and-content-model/troubleshooting-content-type",
        "use": "把故障现象和解决办法放在相关过程附近",
    },
    {
        "id": "GITHUB-REFERENCE",
        "url": "https://docs.github.com/en/contributing/style-guide-and-content-model/reference-content-type",
        "use": "面向快速查值的一致表格和列表结构，不冒充教程",
    },
    {
        "id": "GITHUB-STYLE-GUIDE",
        "url": "https://docs.github.com/en/contributing/style-guide-and-content-model/style-guide",
        "use": "编号过程、前置信息、动作步骤、危险提示和等价文本",
    },
]


def compact_prose(lines: list[str], prose_line_numbers: set[int], start: int, end: int) -> str:
    return "\n".join(
        lines[line_number - 1]
        for line_number in range(start, end + 1)
        if line_number in prose_line_numbers
    )


def detect_entry_signals(text: str) -> dict[str, bool]:
    return {name: bool(pattern.search(text)) for name, pattern in ENTRY_PATTERNS.items()}


def detect_heading_signals(headings: list[str]) -> dict[str, bool]:
    heading_text = "\n".join(headings)
    return {
        name: bool(pattern.search(heading_text))
        for name, pattern in CHAPTER_HEADING_PATTERNS.items()
    }


def candidate_content_type(chapter: dict[str, Any]) -> tuple[str, str]:
    current = str(chapter["content_type"])
    if current != "unclassified":
        return current, "explicit_local_metadata"
    title = str(chapter["title"])
    if REFERENCE_TITLE_RE.search(title):
        return "reference", "title_heuristic"
    if DESIGN_TITLE_RE.search(title):
        return "design-note", "title_heuristic"
    if WORKBOOK_TITLE_RE.search(title):
        return "workbook", "title_heuristic"
    return "instructional", "fallback_candidate"


def candidate_official_profile(
    content_type: str,
    heading_signals: dict[str, bool],
    numbered_step_count: int,
    practice_present: bool,
) -> str:
    if content_type in {"reference", "design-note", "solution", "appendix"}:
        return content_type
    if content_type == "workbook":
        return "task-or-tutorial"
    if numbered_step_count >= 2 or heading_signals["procedure"] or practice_present:
        return "tutorial-like"
    return "concept-like"


def candidate_review_flags(
    chapter: dict[str, Any],
    content_type: str,
    heading_signals: dict[str, bool],
    numbered_step_count: int,
    stateful_candidate: bool,
    official_profile: str,
) -> list[str]:
    flags: list[str] = []
    roles = chapter["roles"]
    if chapter["content_type"] == "unclassified":
        flags.append("content_type_unclassified")
    if official_profile in {"tutorial-like", "task-or-tutorial"}:
        if not heading_signals["prerequisites"]:
            flags.append("candidate_missing_explicit_prerequisites")
        if numbered_step_count < 2 and not heading_signals["procedure"]:
            flags.append("candidate_missing_ordered_procedure")
        if not (
            heading_signals["expected_result"]
            or roles["acceptance"]["explicit_section_present"]
        ):
            flags.append("candidate_missing_expected_result")
        if stateful_candidate and not heading_signals["cleanup"]:
            flags.append("candidate_missing_cleanup_for_stateful_work")
    if official_profile == "concept-like" and not heading_signals["context"]:
        flags.append("candidate_missing_explicit_context")
    if content_type == "instructional":
        for role in ("objectives", "examples", "practice", "acceptance", "sources"):
            if not roles[role]["explicit_section_present"]:
                flags.append(f"candidate_missing_explicit_{role}")
    if content_type == "reference" and not roles["sources"]["explicit_section_present"]:
        flags.append("candidate_reference_without_chapter_source_section")
    return flags


def analyze(
    repository_root: Path,
    pedagogy_report: dict[str, Any],
) -> dict[str, Any]:
    parse_cache: dict[Path, Any] = {}
    documents: list[dict[str, Any]] = []
    chapter_rows: list[dict[str, Any]] = []

    for document in pedagogy_report["documents"]:
        if document["status"] != "active":
            continue
        document_path = repository_root / document["file"]
        parsed_document = parse_cache.setdefault(document_path, parse_markdown(document_path))
        if document["chapter_detection_mode"] == "split_h1":
            preamble_end = min(300, len(parsed_document.lines))
        else:
            preamble_end = (
                min((int(row["start_line"]) for row in document["chapters"]), default=301)
                - 1
            )
        entry_text = compact_prose(
            parsed_document.lines,
            parsed_document.prose_line_numbers,
            1,
            max(1, preamble_end),
        )
        entry_signals = detect_entry_signals(entry_text)
        document_row = {
            "file": document["file"],
            "chapter_count": document["chapter_count"],
            "entry_signals": entry_signals,
            "missing_entry_signals": [
                name for name, present in entry_signals.items() if not present
            ],
        }
        documents.append(document_row)

        for chapter in document["chapters"]:
            source_file = chapter.get("source_file", document["file"])
            source_path = repository_root / source_file
            parsed = parse_cache.setdefault(source_path, parse_markdown(source_path))
            start = int(chapter["start_line"])
            end = int(chapter["end_line"])
            headings = [
                heading.title
                for heading in parsed.headings
                if start <= heading.line <= end
            ]
            heading_signals = detect_heading_signals(headings)
            prose_text = compact_prose(
                parsed.lines,
                parsed.prose_line_numbers,
                start,
                end,
            )
            numbered_step_count = sum(
                bool(NUMBERED_STEP_RE.match(line)) for line in prose_text.splitlines()
            )
            chapter_fences = [
                fence for fence in parsed.fences if start <= fence.start_line <= end
            ]
            tagged_fence_count = 0
            for fence in chapter_fences:
                preceding = "\n".join(
                    parsed.lines[max(start - 1, fence.start_line - 4) : fence.start_line - 1]
                )
                tagged_fence_count += bool(re.search(r"textbook-code:\s*role\s*=", preceding))

            content_type, type_source = candidate_content_type(chapter)
            practice_present = bool(chapter["roles"]["practice"]["explicit_section_present"])
            profile = candidate_official_profile(
                content_type,
                heading_signals,
                numbered_step_count,
                practice_present,
            )
            stateful_candidate = bool(STATEFUL_RE.search(prose_text))
            flags = candidate_review_flags(
                chapter,
                content_type,
                heading_signals,
                numbered_step_count,
                stateful_candidate,
                profile,
            )
            role_presence = {
                role: bool(data["explicit_section_present"])
                for role, data in chapter["roles"].items()
            }
            chapter_rows.append(
                {
                    "document": document["file"],
                    "source_file": source_file,
                    "chapter": chapter["title"],
                    "start_line": start,
                    "end_line": end,
                    "declared_content_type": chapter["content_type"],
                    "candidate_content_type": content_type,
                    "candidate_content_type_source": type_source,
                    "candidate_official_profile": profile,
                    "heading_signals": heading_signals,
                    "role_signals": role_presence,
                    "numbered_step_count": numbered_step_count,
                    "stateful_candidate": stateful_candidate,
                    "code_fence_count": len(chapter_fences),
                    "tagged_code_fence_count": tagged_fence_count,
                    "untagged_code_fence_count": len(chapter_fences) - tagged_fence_count,
                    "review_flags": flags,
                }
            )

    entry_counts = Counter()
    for document in documents:
        entry_counts.update(
            name for name, present in document["entry_signals"].items() if present
        )
    heading_counts = Counter()
    role_counts = Counter()
    profile_counts = Counter()
    flag_counts = Counter()
    for chapter in chapter_rows:
        heading_counts.update(
            name for name, present in chapter["heading_signals"].items() if present
        )
        role_counts.update(
            name for name, present in chapter["role_signals"].items() if present
        )
        profile_counts[chapter["candidate_official_profile"]] += 1
        flag_counts.update(chapter["review_flags"])

    return {
        "schema_version": "1.0",
        "scope": {
            "active_textbook_count": len(documents),
            "active_chapter_count": len(chapter_rows),
            "learner_validation_excluded": True,
        },
        "method": {
            "source_rules": SOURCE_RULES,
            "last_source_access_check": "2026-07-12",
            "interpretation": (
                "Signals and review flags are deterministic candidates based on explicit headings, "
                "numbered steps and local metadata. A missing signal does not prove missing semantics, "
                "and no row is an official certification or learner-effectiveness result."
            ),
        },
        "summary": {
            "entry_signal_document_counts": dict(entry_counts),
            "chapter_heading_signal_counts": dict(heading_counts),
            "chapter_role_signal_counts": dict(role_counts),
            "candidate_official_profile_counts": dict(profile_counts),
            "review_flag_counts": dict(flag_counts),
            "chapter_code_fence_count": sum(row["code_fence_count"] for row in chapter_rows),
            "tagged_code_fence_count": sum(
                row["tagged_code_fence_count"] for row in chapter_rows
            ),
            "untagged_code_fence_count": sum(
                row["untagged_code_fence_count"] for row in chapter_rows
            ),
        },
        "documents": documents,
        "chapters": chapter_rows,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    signal_names = list(CHAPTER_HEADING_PATTERNS)
    role_names = ("objectives", "examples", "counterexamples", "practice", "acceptance", "sources")
    fieldnames = [
        "document",
        "source_file",
        "chapter",
        "start_line",
        "end_line",
        "declared_content_type",
        "candidate_content_type",
        "candidate_content_type_source",
        "candidate_official_profile",
        *[f"heading_{name}" for name in signal_names],
        *[f"role_{name}" for name in role_names],
        "numbered_step_count",
        "stateful_candidate",
        "code_fence_count",
        "tagged_code_fence_count",
        "untagged_code_fence_count",
        "review_flags",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flattened = {key: value for key, value in row.items() if key not in {"heading_signals", "role_signals", "review_flags"}}
            flattened.update(
                {f"heading_{name}": row["heading_signals"][name] for name in signal_names}
            )
            flattened.update(
                {f"role_{name}": row["role_signals"][name] for name in role_names}
            )
            flattened["review_flags"] = ";".join(row["review_flags"])
            writer.writerow(flattened)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("pedagogy_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()

    repository_root = args.repository_root.resolve()
    pedagogy_report = json.loads(args.pedagogy_json.read_text(encoding="utf-8-sig"))
    report = analyze(repository_root, pedagogy_report)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(args.output_csv, report["chapters"])
    print(
        json.dumps(
            {
                "status": "ok",
                "active_textbook_count": report["scope"]["active_textbook_count"],
                "active_chapter_count": report["scope"]["active_chapter_count"],
                "output_json": str(args.output_json),
                "output_csv": str(args.output_csv),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
