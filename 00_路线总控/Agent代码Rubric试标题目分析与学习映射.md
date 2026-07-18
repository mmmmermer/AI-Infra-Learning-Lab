# Agent 代码 Rubric 试题分析与学习映射（抽象版）

## 来源

本页依据用户提供的一份本地练习表做抽象总结。原始表格、在线文档和任何需要登录或权限的
内部链接不随仓库发布；本页只保留随仓库公开展示的作者自有概括，不提供源材料定位信息。
来源与再分发边界登记为治理台账资产 `EXT-RUBRIC-001`；该登记不授予原始材料或本页内容的额外许可。

## 题目内容概括

Excel 只有一个工作表，核心信息是：

1. rubric 是给 Agent 任务结果设置打分点。
2. rubric 需要打三类标签：
   - 优先级：Must / Nice。
   - 类型：Objective / Subjective。
   - 必要性：Explicit / Implicit。
3. rubric 只检查产物和端口结果，不检查 Agent 行为过程。
4. 对客观结果要核对具体路径、数字和值。
5. 如果结果需要访问端口，也要验证端口输出。
6. 示例 task 是：根据给定资料更新一个产品设计文档，并核对章节、版本、日期和发布位置；具体产品、厂商和内部系统名称不属于本公开摘要。

## 它训练的能力是什么

这份材料不是金融工程题，也不是量化题。

它训练的是：

```text
Agent 任务结果评测
-> rubric 设计
-> 客观/主观检查点拆分
-> 显式/隐式要求识别
-> 文件产物验证
-> 端口/API 输出验证
-> 数字和值核对
```

它和本库最相关的是 AI 输出质量评测线、M04 Agent 工作流、M11 实验设计、P03 EvaluationTask，而不是 F 系列金融工程主线。

## 是否值得学习

值得，但不能放错位置。

值得的原因：

- 它训练“怎么评价 Agent 是否完成任务”，这正好是 P03 后续需要的 `EvaluationTask` 和 `ReviewRecord` 能力。
- 它强调 Objective / Subjective、Must / Nice、Explicit / Implicit，这适合转化为 M11 的 rubric 设计方法。
- 它要求检查文件、端口、具体数值，这能补足 AI 工程里常见的“只看模型回答、不验证产物”的问题。
- 它和 RAG/Agent 质量评测、代码生成评测、AI 标注岗位都有关系。

不应该误用的地方：

- 不要把它当作金融工程核心内容。
- 不要把它当成代码能力本身。
- 不要把“会写 rubric”包装成已经会做 Agent 平台。
- 不要替代 Python、测试、API、项目复现这些基础能力。

## 应该映射到哪些模块

| 学习板块 | 映射方式 | 需要补的能力 |
|---|---|---|
| M04 Agent 工作流 | 评估 Agent 任务是否正确完成 | step_logs、工具调用、产物验证 |
| M11 科研方法与实验设计 | 设计 rubric、baseline、人工评测记录 | Must/Nice、Obj/Subj、Explicit/Implicit |
| M08 监控压测与可观测性 | 区分性能指标和质量指标 | latency 不是 correctness |
| P03 AI Workload Platform | planned EvaluationTask / ReviewRecord 思路（v0.3.1 未实现） | 产物检查、端口检查、值核对 |
| M01 Python 工程能力 | 代码和文件结果检查 | pytest、路径、JSON、数值断言 |
| AI 输出质量评测能力线 | 作为评测任务样例 | Rubric 设计和人工复核 |

## 可以转化成的学习任务

### R11-01 Rubric 标签拆解练习

输入一个 Agent task，拆出：

- Must / Nice。
- Objective / Subjective。
- Explicit / Implicit。
- 对应验证方式。

输出一张 rubric 表。

### R11-02 产物验证练习

给定一个任务要求，检查：

- 文件是否存在。
- 版本号是否正确。
- 日期字段是否正确。
- 指定章节是否被更新。
- JSON/Markdown/文档字段是否匹配。

### R11-03 端口/API 验证练习

给定一个本地服务任务，检查：

- 服务是否可访问。
- endpoint 是否返回指定字段。
- 数字和值是否符合要求。
- 错误状态是否被记录。

### R11-04 Agent 任务评分记录

建立一个简化 `ReviewRecord`：

```text
task_id
rubric_item
priority
type
necessity
verification_method
expected_value
actual_value
pass_fail
reviewer_note
```

## 和金融工程第二主线的关系

它和 F 系列不是同一条线，但未来可以交叉。

交叉方式：

```text
金融 RAG / 金融回测 / 风险指标任务
-> 产物输出
-> Rubric 检查
-> ReviewRecord
-> P03 质量评测
```

例如：

| 金融任务 | Rubric 检查点 |
|---|---|
| 风险指标计算 | VaR 数值是否和公式/样例一致 |
| 回测任务 | 是否记录交易成本和数据泄漏检查 |
| 金融 RAG | 是否引用来源，单位和时间口径是否正确 |
| pricing task | 输入参数、随机种子、模拟次数是否记录 |

## 对当前路线的处理建议

1. 不新增 M13。
2. 保留在 `AI 输出质量评测能力线` 和 M11/P03 中。
3. 后续进入 P03 时，再把它转成 planned `EvaluationTask` 和 `ReviewRecord` 字段。
4. 后续进入金融工程 F08 时，用它检查金融 task 的输出质量。
5. 当前不抢 M00/M01/P01/M05 起步学习。

## 结论

这份题目值得学习，但它的价值不是“金融代码标注”，而是：

```text
训练你把 Agent 任务拆成可验证的评分标准，
并用文件、端口、字段、数字和值来验证产物。
```

它应该进入：

```text
M11 Rubric / 人工评测
M04 Agent 工作流评测
P03 EvaluationTask / ReviewRecord
AI 输出质量评测能力线
```

只在未来金融任务接入 P03 后，作为金融 task 输出质量检查方法使用。
