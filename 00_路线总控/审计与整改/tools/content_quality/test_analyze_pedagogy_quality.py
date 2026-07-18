from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analyze_pedagogy_quality import (
    UNCLASSIFIED_CONTENT_TYPE,
    analyze_document,
    build_summary,
)


class PedagogyContentTypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def analyze(self, markdown: str) -> dict[str, object]:
        path = self.root / "10_学习模块" / "T00_测试_适配教材.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return analyze_document(path, self.root)

    def test_document_default_and_chapter_override(self) -> None:
        document = self.analyze(
            """# 测试教材

<!-- textbook-content: default=instructional -->

## 第一章：核心概念

### 学习目标

能解释核心概念。

## 第二章：来源索引

<!-- textbook-content: type=appendix -->

### 资料来源

列出来源。
"""
        )

        self.assertEqual(document["default_content_type"], "instructional")
        self.assertEqual(
            [chapter["content_type"] for chapter in document["chapters"]],
            ["instructional", "appendix"],
        )
        self.assertEqual(
            document["chapters"][1]["content_type_source"], "chapter_marker"
        )

    def test_unmarked_legacy_document_is_unclassified_without_error(self) -> None:
        document = self.analyze(
            """# 旧教材

## 第一章：旧内容

正文。
"""
        )

        self.assertEqual(document["default_content_type"], UNCLASSIFIED_CONTENT_TYPE)
        self.assertEqual(
            document["chapters"][0]["content_type"], UNCLASSIFIED_CONTENT_TYPE
        )
        self.assertEqual(document["content_type_issues"], [])

    def test_unknown_chapter_marker_does_not_hide_behind_default(self) -> None:
        document = self.analyze(
            """# 测试教材

<!-- textbook-content: default=instructional -->

## 第一章：错误标记

<!-- textbook-content: type=guide -->

正文。
"""
        )
        chapter = document["chapters"][0]

        self.assertEqual(chapter["content_type"], UNCLASSIFIED_CONTENT_TYPE)
        self.assertEqual(chapter["content_type_source"], "invalid_marker")
        self.assertEqual(
            chapter["content_type_issues"][0]["kind"], "unknown_content_type"
        )
        summary = build_summary([document])
        self.assertEqual(summary["active_content_type_issue_count"], 1)

    def test_conflicting_explicit_markers_are_unclassified(self) -> None:
        document = self.analyze(
            """# 测试教材

## 第一章：冲突标记 [reference]

<!-- textbook-content: type=appendix -->

正文。
"""
        )
        chapter = document["chapters"][0]

        self.assertEqual(chapter["content_type"], UNCLASSIFIED_CONTENT_TYPE)
        self.assertEqual(chapter["content_type_source"], "conflicting_markers")
        self.assertEqual(
            chapter["content_type_issues"][0]["kind"],
            "conflicting_content_types",
        )

    def test_heading_and_quote_metadata_are_supported(self) -> None:
        document = self.analyze(
            """# 测试教材

## 第一章：接口手册 [reference]

正文。

## 第二章：独立练习

> 内容类型：`workbook`

正文。
"""
        )

        self.assertEqual(
            [chapter["content_type"] for chapter in document["chapters"]],
            ["reference", "workbook"],
        )

    def test_fenced_marker_is_not_metadata(self) -> None:
        document = self.analyze(
            """# 测试教材

```markdown
<!-- textbook-content: default=instructional -->
```

## 第一章：正文

正文。
"""
        )

        self.assertEqual(
            document["chapters"][0]["content_type"], UNCLASSIFIED_CONTENT_TYPE
        )

    def test_primary_role_coverage_only_uses_instructional_chapters(self) -> None:
        document = self.analyze(
            """# 测试教材

<!-- textbook-content: default=instructional -->

## 第一章：核心概念

### 学习目标

能解释核心概念。

## 第二章：学习顺序

<!-- textbook-content: type=appendix -->

这里只提供导航。
"""
        )
        summary = build_summary([document])

        self.assertEqual(summary["active_instructional_chapter_count"], 1)
        self.assertEqual(summary["role_coverage"]["objectives"]["chapter_count"], 1)
        self.assertEqual(summary["role_coverage"]["objectives"]["coverage_ratio"], 1.0)
        self.assertEqual(
            summary["all_active_role_coverage"]["objectives"]["coverage_ratio"],
            0.5,
        )
        self.assertEqual(
            summary["role_coverage_by_content_type"]["appendix"]["objectives"]
            ["chapter_count"],
            1,
        )

    def test_established_worked_example_and_practice_headings_are_detected(self) -> None:
        document = self.analyze(
            """# 测试教材

<!-- textbook-content: default=instructional -->

## 第一章：数值推演

### Worked example：固定输入

展示中间状态。

### 独立变式

更换输入后重做。

## 第二章：环境观察

### 观察实验：制造并恢复故障

保存诊断证据。
"""
        )

        first, second = document["chapters"]
        self.assertTrue(first["roles"]["examples"]["explicit_section_present"])
        self.assertTrue(first["roles"]["practice"]["explicit_section_present"])
        self.assertTrue(second["roles"]["practice"]["explicit_section_present"])

    def test_chapter_local_source_heading_is_detected(self) -> None:
        document = self.analyze(
            """# 测试教材

<!-- textbook-content: default=instructional -->

## 第一章：统计口径

### 本章来源

使用官方文档核对定义与版本边界。
"""
        )

        chapter = document["chapters"][0]
        self.assertTrue(chapter["roles"]["sources"]["explicit_section_present"])


if __name__ == "__main__":
    unittest.main()
