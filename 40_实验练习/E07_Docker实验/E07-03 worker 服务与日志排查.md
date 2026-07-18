# E07-03 独立 worker 与日志排查

> 参考状态（2026-07-10）：独立 worker、重复投递 CAS 和过期租约恢复已在真实 Compose 中验证。学习者复现状态仍未完成。

## 实验目的

把 E07-02 的持久化入队推进为完整后台执行链路：

```text
Redis Streams XREADGROUP reserve task_id
-> PostgreSQL CAS: queued -> running
-> 记录 worker_id、lease_until 和 claim version
-> 执行 mock workload
-> owner/version/lease-checked CAS: running -> succeeded/failed
-> 数据库终态成功后 XACK
```

API 和 worker 不共享内存；Compose 模式下 `POST /workers/run-next` 会拒绝调用，任务只能由独立 worker 自动消费。

## 参考实现位置

- `app/worker_service.py`：阻塞消费、任务认领、执行和回写。
- `app/worker.py`：确定性 mock workload。
- `app/postgres_store.py`：认领、完成、失败、租约恢复 CAS。
- `scripts/verify_compose.ps1`：正常和故障路径。

## 状态与所有权

| 操作 | 必须满足 | 更新 |
|---|---|---|
| 认领任务 | `status = queued` | `running`、`worker_id`、`lease_until`、递增 `version` |
| 成功完成 | `running` 且 owner/version/未过期 lease 匹配 | `succeeded`、result、runtime |
| 失败完成 | `running` 且 owner/version/未过期 lease 匹配 | `failed` 或 `retrying` |
| 租约恢复 | `running` 且 lease 过期 | `retrying` + 新 outbox，或重试耗尽后 `failed` |

仅凭 Redis 拿到消息不代表 worker 获得执行权，数据库 CAS 才是最终裁决。

## 正常与失败路径

普通任务最终应为：

```text
pending -> queued -> running -> succeeded
```

设置 `input_json.force_error=true` 的确定性失败不重试：

```text
pending -> queued -> running -> failed
error_type = forced_failure
```

查看状态与日志：

```powershell
docker compose logs worker
docker compose logs dispatcher
Invoke-RestMethod http://127.0.0.1:8001/tasks/<task_id>
```

## 重复投递验证

transactional outbox 提供至少一次投递，而不是恰好一次。向 Redis Stream 人工再次放入已成功的 `task_id`：

```powershell
docker compose exec -T redis redis-cli XADD p03:tasks:stream:v1 "*" task_id <task_id>
```

worker 会 reserve 消息，但 `queued -> running` CAS 返回空；任务保持 `succeeded`，`delivery_count`
不增加，workload 不再次执行。worker 会 ACK 这条已判定为 duplicate/stale 的消息。

## reserve 后崩溃与 pending reclaim

Streams consumer group 不会在读取时删除消息。worker 在 `XREADGROUP` 后、数据库 claim 前退出时，
消息仍在 pending entries list；其他 consumer 在 idle 超过 worker lease 后使用 `XAUTOCLAIM`
重新取得它。只有数据库终态成功写入后才执行 `XACK + XDEL`。这关闭了旧 `BLPOP` 在 pop 后、
claim 前崩溃会永久丢消息的窗口。

## worker 中断与租约恢复

参考 workload 允许最多 5 秒的 `sleep_ms`，Compose worker lease 为 8 秒。故障验证步骤：

```text
提交 sleep_ms=5000 的任务
-> 等任务进入 running
-> docker compose stop worker
-> 等 lease 过期
-> docker compose start worker
-> reconciliation 写 retry outbox
-> dispatcher 重新投递
-> 新 worker 完成任务
```

验证后数据库应显示该任务：

```text
status = succeeded
retry_count = 1
delivery_count = 2
```

这证明 worker 进程退出不会永久留下 `running` 任务。真实长任务仍需要周期 heartbeat；当前 mock workload 因上限小于 lease，没有启动 heartbeat 线程。

## 日志排查矩阵

| 现象 | 证据 | 判断 |
|---|---|---|
| task 一直 `pending` | dispatcher 无 publish | outbox 尚未投递 |
| task 一直 `queued` | worker/Redis consumer group | 新消息未投递或 pending 尚未 reclaim |
| task 一直 `running` | `lease_until`、worker 日志 | worker 中断或 finalize 失败 |
| 同一 task_id 多次出现 | worker 的 duplicate/stale 日志 | 至少一次投递的正常可能性 |
| finalize CAS 失败 | owner/status/version/lease | 租约过期、claim 已被替换或任务已终态 |
| 反复 retrying | retry_count、error_type | 瞬时错误持续或重试策略不当 |

## 自动参考验证

```powershell
.\scripts\verify_compose.ps1
```

脚本会主动停启 worker 并检查数据库计数，不以“容器仍在运行”替代任务恢复证据。

## 参考验收证据

- [x] worker 是独立 Compose 服务且不暴露宿主机端口。
- [x] worker 通过服务名访问 PostgreSQL 和 Redis。
- [x] 成功和确定性失败均能持久化最终状态。
- [x] 重复 Redis 消息不会重复执行终态任务。
- [x] worker 中断后可经 lease + outbox 恢复。
- [x] worker/dispatcher/API 日志未留下未处理 traceback。

## 学习者验收

- [ ] 亲自观察一次 `pending -> queued -> running -> succeeded`。
- [ ] 亲自制造并解释一次 `forced_failure`。
- [ ] 亲自完成一次重复投递去重检查。
- [ ] 亲自完成一次 worker 中断与租约恢复。
- [ ] 能解释至少一次投递、CAS、lease 和 heartbeat 的关系。

## 边界提醒

CAS 只防止平台重复认领同一任务。真实 workload 若会发邮件、扣款或写外部系统，还必须为外部副作用设计单独的幂等键或事务边界。
