# E02-03 metrics API

## 目标

从共享 repository 按服务端 principal 动态生成 `GET /metrics`，完成“认证 -> 创建任务 -> 查询任务
-> 本人指标变化”的累计闭环。

## 输出

```json
{
  "task_count": 1,
  "status_counts": {
    "pending": 1,
    "queued": 0,
    "running": 0,
    "succeeded": 0,
    "failed": 0,
    "retrying": 0,
    "cancelled": 0
  }
}
```

metrics 不能是启动时写死的常量。每次请求都从 repository 当前状态按 tenant/owner 聚合，不能
因为它是汇总接口就绕过资源边界。

## 端到端验收

1. 首次 `GET /metrics` 的 `task_count` 为 0。
2. `POST /tasks` 创建任务。
3. `GET /tasks/{task_id}` 返回该任务。
4. 再次 `GET /metrics`，`task_count` 和 `pending` 均增加到 1。
5. Bob 使用自己的 fixture credential 查询，`task_count` 仍为 0。

自动验证位于 `e02_service/tests/test_api.py`。2026-07-13 在 Python 3.13 下全套 12 个测试通过，
其中 11 个运行时契约测试、1 个 OpenAPI schema 测试；准确数量以当次 pytest 输出为准。

## 边界

E02 不模拟 worker，也不把任务假装成 `succeeded`。状态执行、队列和恢复由 P03/M06 后续实验负责。
