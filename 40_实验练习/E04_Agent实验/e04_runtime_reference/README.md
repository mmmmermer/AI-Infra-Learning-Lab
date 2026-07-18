# E04 确定性 Agent Runtime 参考实现

本目录把 E04-01、E04-02、E04-03 和 E04-05 的关键契约做成可执行、无网络的教学
reference。它使用固定 planner、内存 repository、手动时钟和 mock 工具，不调用 LLM，也不依赖
P03、Redis 或数据库。

## 已实现边界

- 请求 schema 拒绝客户端提交 tenant、owner、scope、permission、审批人和目标哈希。
- `Principal` 只由已验证 claims 构造；工具执行同时检查 capability 与 resource grant。
- RAG 文档在排序前按授权 source ID 过滤；工具输出继续标记为不可信数据。
- task `status` 与 `current_step` 分离，审批拒绝和超时进入带错误类型的 `failed`。
- 审批绑定 workflow、draft、action、版本和到期时间；决策使用 approval version CAS。
- 批准事务产生 resume outbox；worker claim 带 owner、claim version 和 lease fencing。
- 副作用以 approval ID 幂等；租约重领后旧 claim 不能 finalize，新 claim 必须重新取得执行证据。
- session 以 tenant、owner、session ID 复合键隔离，并用 `expected_version` 防止丢失更新。
- 运维审计对 query、message、comment、token 和主体字段脱敏；审批决策另存不可变领域事件。

## 运行

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q
```

2026-07-18 的本地 reference 验证结果为 `38 passed`。这只证明本目录的确定性契约测试，
不表示学习者已经完成实验。

## 未证明的能力

- 这里的 `RLock` 只模拟单进程事务边界，不替代数据库行锁、隔离级别和持久化 outbox。
- 没有真实队列 relay、跨进程 crash recovery、生产认证、策略引擎、egress sandbox 或 tracing backend。
- 没有任意模型抵抗 prompt injection 的证明；安全保证来自模型外 schema、ACL、capability gate、
  审批和幂等边界。
- P03 `v0.3.1` 仍只提供 `mock_agent` workload，不包含 `/agent/*` 或本 runtime 的生产集成。
