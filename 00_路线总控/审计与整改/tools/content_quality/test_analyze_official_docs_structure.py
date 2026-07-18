from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analyze_official_docs_structure import (
    analyze,
    candidate_content_type,
    detect_entry_signals,
    detect_heading_signals,
)
from analyze_pedagogy_quality import analyze_document


class OfficialDocsStructureTests(unittest.TestCase):
    def test_entry_signals_are_explicit(self) -> None:
        signals = detect_entry_signals(
            "目标读者：Python 初学者。前置：Python 3.13。预计学习时间 30 分钟。"
            "学习产物：result.json。完成标准：命令返回 0。学习顺序：先概念后实验。"
        )

        self.assertTrue(signals["audience"])
        self.assertTrue(signals["prerequisites"])
        self.assertTrue(signals["version"])
        self.assertTrue(signals["estimated_time"])
        self.assertTrue(signals["outputs"])
        self.assertTrue(signals["completion"])
        self.assertTrue(signals["navigation"])
        self.assertFalse(signals["content_type"])

    def test_chapter_heading_signals_do_not_use_body_keywords(self) -> None:
        signals = detect_heading_signals(
            ["第一章：服务", "背景与目标", "操作步骤", "预期输出", "故障排查", "清理"]
        )

        self.assertTrue(signals["context"])
        self.assertTrue(signals["procedure"])
        self.assertTrue(signals["expected_result"])
        self.assertTrue(signals["troubleshooting"])
        self.assertTrue(signals["cleanup"])
        self.assertFalse(signals["summary"])

    def test_unclassified_reference_title_is_only_a_candidate(self) -> None:
        content_type, source = candidate_content_type(
            {"content_type": "unclassified", "title": "第 8 章：字段参考"}
        )

        self.assertEqual(content_type, "reference")
        self.assertEqual(source, "title_heuristic")

    def test_analysis_excludes_learner_validation_and_keeps_candidate_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "10_学习模块" / "T00_测试_适配教材.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                """# 测试教材

目标读者：Python 初学者。

<!-- textbook-content: default=instructional -->

## 第一章：创建服务

### 学习目标

能够创建服务。

### 操作步骤

1. 创建文件。
2. 运行服务。

### 预期输出

状态为 ready。

### 练习

更换端口。
""",
                encoding="utf-8",
            )
            document = analyze_document(path, root)
            report = analyze(
                root,
                {
                    "documents": [document],
                },
            )

        self.assertTrue(report["scope"]["learner_validation_excluded"])
        self.assertEqual(report["scope"]["active_chapter_count"], 1)
        row = report["chapters"][0]
        self.assertEqual(row["numbered_step_count"], 2)
        self.assertEqual(row["candidate_official_profile"], "tutorial-like")
        self.assertIn("candidate_missing_explicit_prerequisites", row["review_flags"])


if __name__ == "__main__":
    unittest.main()
