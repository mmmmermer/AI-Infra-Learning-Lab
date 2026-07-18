# E04 确定性 Agent Runtime 参考实现

本目录把 E04-01、E04-02、E04-03 和 E04-05 的关键契约做成可执行、无网络的教学
reference。它使用固定 planner、内存 repository、手动时钟和 mock 工具，不调用 LLM，也不依赖
P03、Redis 或数据库。

## 已实现边界

- 请求 schema 拒绝客户端提交 tenant、owner、scope、permission、审批人和目标哈希。
- `Principal` 只由已验证 claims 构造；工具执行同时检查 capability 与 resource grant。
- RAG 文档在排序前按授权 source ID 过滤；工具输出继续标记为不可信数据。
- task `status` 与 `current_step` 分离，审批拒绝和超时进入带错误类型的 `failed`。
- 显式取消使用 task version CAS，形成 `cancelled` 终态并关闭 pending approval/outbox；worker 观察到取消后不能改写为 `failed`。
- 审批绑定 workflow、draft、action、版本和到期时间；决策使用 approval version CAS。
- 批准事务产生 resume outbox；worker 必须提交服务端可信 tenant scope，claim 带 tenant、owner、claim version 和 lease fencing。
- 副作用 handler 前先在共享 repository 原子标记 `effect_started`，再以 approval ID 幂等执行并标记 `effect_executed`。取消先提交时 handler 不会执行；开始栅栏先提交时拒绝硬取消。租约重领后旧 claim 不能 finalize，新 claim 必须重新取得执行证据。
- `ToolSpec` 可声明 URL/path resolver；统一策略默认拒绝网络与文件目标，exact origin 和 root containment 校验在 handler 前执行。
- 非预期 handler 异常归一为 `invalid_tool_output`；取消、终态失败和可重试 step 失败都有运行事件。
- session 以 tenant、owner、session ID 复合键隔离，并用 `expected_version` 防止丢失更新。
- 运维审计递归隐藏 credential、query、message、comment、URL、路径、payload 和 tool output；只有精确命名且满足 bool/int/fixed-hex 合同的元数据可保留，未知嵌套字段默认隐藏；审批决策另存不可变领域事件。

## 代码入口

| 文件 | 负责什么 |
|---|---|
| `e04_runtime/runtime.py` | 有限两步工作流、取消入口、审批恢复和失败归一化 |
| `e04_runtime/repository.py` | CAS 状态迁移、approval/outbox/lease、副作用标记和领域事件 |
| `e04_runtime/tools.py` | 严格工具 schema、capability/resource 授权与 handler 边界 |
| `e04_runtime/security.py` | 默认拒绝的 exact-origin URL 与 root-confined path validator |
| `e04_runtime/audit.py` | 递归脱敏、限长的运维 trace |

## 运行

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q
```

2026-07-18 的本地 reference 验证结果为 `76 passed`、`0 skipped`。这只证明本目录的确定性契约测试，
不表示学习者已经完成实验。

定向证据：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_cancellation_and_injection.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_target_security.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_sessions_and_audit.py
```

- `test_cancellation_and_injection.py`：cancel CAS、审批/outbox 联动、副作用栅栏、异常审计、恶意工具输出。
- `test_approval_workflow.py`：审批 CAS、初始消息幂等重投、tenant-scoped claim、lease reclaim 与 finalize fencing。
- `test_target_security.py`：默认 deny egress/path、SSRF、编码/绝对/UNC/盘符路径、解析后符号链接逃逸。
- `test_sessions_and_audit.py`：tenant/owner/session/CAS 与嵌套 trace 脱敏。

## 未证明的能力

- 这里的 `RLock` 只模拟单进程事务边界，不替代数据库行锁、隔离级别和持久化 outbox。
- 没有真实队列 relay、跨进程 crash recovery、生产认证、策略引擎、HTTP client、egress sandbox 或 tracing backend。
- URL validator 证明静态 origin/IP literal 边界，不执行 DNS 解析或重定向；生产客户端必须对每次解析结果和 redirect 重新校验并在网络层阻断私网/metadata。
- Path validator 会检查解析后 containment；reference 不替代操作系统沙箱、只读挂载、文件描述符级防竞态或 TOCTOU 防护。
- `effect_started/effect_executed` 是内存教学 repository 中的共享事实，不是生产持久化证明；生产系统必须在数据库事务中提交开始栅栏，把幂等键、外部结果与 outbox 状态持久化，并为开始后崩溃、未知或部分副作用设计对账/补偿。
- 没有任意模型抵抗 prompt injection 的证明；安全保证来自模型外 schema、ACL、capability gate、
  审批和幂等边界。
- P03 `v0.3.1` 仍只提供 `mock_agent` workload，不包含 `/agent/*` 或本 runtime 的生产集成。
