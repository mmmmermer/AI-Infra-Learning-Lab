# Content Quality Audit Artifacts

Status: `open-source cross-check completed / findings require calibrated interpretation`.

Current author-side structure snapshot after the recorded Wave 2 chapter edits:

- 22 active textbooks, one archived draft and 202 detected active chapters.
- 1,527 code fences and 360 visual items in active textbooks.
- All 202 chapters are classified: 158 `instructional`, two `workbook`, four
  `reference`, 27 `design-note`, and 11 `appendix`; there are no unclassified
  chapters or content-type conflicts.
- The 158 `instructional` chapters currently expose 135 explicit objectives,
  61 worked examples, 112 counterexamples, 108 practice sections, 121
  acceptance sections, and 39 chapter-local source sections.
- 34 Mermaid diagrams are present, of which six currently carry the
  analyzer's explicit accessibility metadata signal.

Latest complete open-source-tool audit snapshot, rerun after both recorded
Wave 2 chapter batches:

- 106 Markdownlint findings and 7,295 Zhlint suggestions, both advisory.
- 34 raw Vale candidates, with zero confirmed content errors after manual review.
- 311 unique URLs; 25 network/access anomalies and zero confirmed 404/410.
- zero Codespell findings and zero tracked-history Gitleaks private-key findings.
- 16 jscpd Markdown review candidates: 253 duplicated lines and 7,622 duplicated tokens;
  Python duplicate candidates are zero. These remain manual-review candidates, not deletion orders.
- 30 documents with Mermaid rendered successfully; zero render failures.

The directory contains raw outputs from that complete tool run:

- Markdownlint CLI2 0.23.0.
- Zhlint 0.8.2 over a line-preserving sanitized Markdown mirror.
- Vale 3.15.1 with repository-specific rules.
- Codespell 2.4.2 for English technical-token typos.
- Lychee 0.24.2.
- Gitleaks 8.30.1 for tracked-history private-key detection.
- jscpd 5.0.12 for duplicate review candidates.
- the repository whole-file and chapter-aware textbook analyzers.
- the official technical learning-document structure candidate analyzer and its 202-row CSV.
- Mermaid CLI 11.16.0 through the separate on-demand render validator.

`markdownlint` and `zhlint` return nonzero when they find suggestions. Vale exit
code zero does not mean zero raw candidates; inspect `vale.json`. `lychee`
returns nonzero for access-restricted and protocol errors as well as broken
links. Gitleaks' tracked-history private-key rule is a release-scope gate; the
separate workspace scan also sees ignored local Obsidian and kind credentials,
which must never be included in a zip or other workspace export. Read
`05_教材内容质量大检查报告_2026-07-11.md` and
`06_教材教学有效性与工具复核报告_2026-07-11.md` for classified results; do not
treat raw counts as confirmed content defects.

The `.tools/content-quality/zhlint-input/` mirror is generated and ignored. It
removes code blocks, URLs and WikiLink targets so Zhlint does not lint them as
Chinese prose.

`pedagogy_analysis.json` in this directory preserves the latest complete
open-source-tool run. The matching author-side structure snapshot is recorded in
`../official_docs_content_audit_2026-07-12/official_docs_structure.json` and
`chapter_matrix.csv`. Missing explicit role sections are review candidates,
not proof that the prose lacks the concept. All 22 module entries expose
audience, prerequisites, scope, version boundary, estimated time, outputs,
completion criteria, navigation, and content type. These are explicit
structure signals, not textbook quality or learning-effect scores.

`official_docs_structure.json` explicitly excludes learner trials, personal
reproduction, pre/post tests, transfer tests and delayed retention. It records
author-side structure candidates only. The analyzer suite currently has 13
unit tests; `tool_exit_codes.json` records the exit status of the complete tool run.
