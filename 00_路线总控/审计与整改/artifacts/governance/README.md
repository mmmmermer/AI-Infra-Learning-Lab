# 治理资产与门禁

本目录保存可机器检查的发布治理资产，不表示自动完成法律判断、学习者验证或工程验收。

## 文件

- `optimization_matrix_status_evidence.csv`：为全部非 `planned` 状态保存原因与证据，避免改变
  `11_教材内容优化任务矩阵.csv` 的固定 17 列结构。2026-07-19 的证据审计结果为
  `completed` 25 项、`in-progress` 7 项、`blocked` 2 项、`planned` 76 项。
- `optimization_matrix_status_audit_2026-07-19.md`：记录逐状态判定规则、任务清单和未完成条件。
- `provenance_license_ledger.csv`：按资产类别登记来源、版本、许可/条款、修改情况、再分发判断、
  证据和复核日期。`unknown / review-required` 是明确的未决状态，不是许可结论。
- `version_manifest.json`：记录运行时、依赖、服务、集群、推理系统和内容检查工具的当前基线与边界。
- `version_resolution_2026-07-18.json`：本机版本观察记录，只作清单复核证据，不替代依赖锁文件。

来源台账当前有 35 项登记，其中 1 项第三方 bundle 已完成许可证核验，其余 34 项仍为
`review-required`。校验通过只证明台账结构、证据路径和状态逻辑有效，不代表这些未决项已经
获得再分发批准。

## 本地检查

```powershell
py -3.13 .\00_路线总控\审计与整改\tools\validate_optimization_matrix.py .
py -3.13 .\00_路线总控\审计与整改\tools\validate_provenance_ledger.py .
py -3.13 .\00_路线总控\审计与整改\tools\validate_version_manifest.py .
```

矩阵校验会检查 110 行、17 列、必填字段、ID/优先级/状态枚举、内部依赖存在性、循环、
P0 对 P2/P3 的排期倒挂、完成任务的未完成前置，以及阻塞/完成状态的独立证据。分号分隔的
描述型知识或环境前置会保留在报告中，但不会被误当成矩阵任务 ID。

版本清单默认按每项 `max_age_days` 阻断过期记录。vLLM、NVIDIA Triton Inference Server
和 Triton language/compiler 当前没有已选执行版本，必须保持 `blocked` 或 `design-only`，
直到对应环境、兼容矩阵和可复现证据成立。
