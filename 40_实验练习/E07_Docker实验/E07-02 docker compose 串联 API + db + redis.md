# E07-02 Docker Compose 串联 API + db + Redis

> 参考状态（2026-07-10）：P03 v0.2 已在 Docker Desktop 上从空卷构建并验证。这里的勾选表示 reference 证据，不表示学习者已完成实验。

## 实验目的

把 API、PostgreSQL 和 Redis 串成可复现服务组，同时避免经典的“双写”错误：API 不能先写数据库、再直接写 Redis，并假定两步必然同时成功。

当前参考链路是：

```text
POST /tasks
-> PostgreSQL 同一事务写 tasks(status=pending) + outbox
-> dispatcher 租约认领 outbox
-> task 改为 queued
-> Redis 只接收 task_id
-> outbox 标记 published
```

dispatcher 在 Redis 写入后、数据库确认前崩溃时可能重复投递，因此 E07-03 的 worker 必须用数据库 CAS 去重。

## 参考实现位置

```text
50_项目产出/P03_AI_Workload_Platform/p03_service/
├─ app/main.py
├─ app/postgres_store.py
├─ app/redis_queue.py
├─ app/dispatcher.py
├─ database/init.sql
├─ Dockerfile
├─ compose.yaml
└─ scripts/verify_compose.ps1
```

## 服务和数据所有权

| 服务 | 职责 | 是否保存任务事实 |
|---|---|---|
| `api` | 校验请求、事务提交 task/outbox、查询状态 | 否 |
| `db` | 保存 task、outbox、状态、租约和结果 | 是，唯一事实源 |
| `redis` | 至少一次传递 `task_id` | 否 |
| `dispatcher` | 把未发布 outbox 事件送到 Redis | 否 |
| `worker` | E07-03 中消费并执行任务 | 否 |

Redis list 长度只是 broker backlog，不等于数据库中所有 `queued` 任务数量。

## 启动与检查

```powershell
cd 50_项目产出\P03_AI_Workload_Platform\p03_service
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/ready
```

`/health` 只证明 API 进程存活；`/ready` 才检查 PostgreSQL 和 Redis。

创建任务：

```powershell
$body = @{
    task_type = "mock_rag"
    priority = 5
    estimated_duration_ms = 10
    idempotency_key = "e07-02-demo-001"
    input_json = @{ query = "什么是 transactional outbox？" }
} | ConvertTo-Json -Depth 5

$submission = Invoke-RestMethod `
    http://127.0.0.1:8001/tasks `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

$submission.task.task_id
```

## 持久性与积压验证

停止 dispatcher 后提交任务：

```powershell
docker compose stop dispatcher
# 再提交一个使用新 idempotency_key 的任务
```

此时任务应保留为 `pending`，outbox 仍在 PostgreSQL。重新启动 dispatcher 后，任务应继续进入 Redis 和 worker：

```powershell
docker compose start dispatcher
```

重启 API 后，既有任务仍应可查询：

```powershell
docker compose restart api
Invoke-RestMethod http://127.0.0.1:8001/tasks/<task_id>
```

这两项分别证明 outbox 积压不会因 dispatcher 暂停丢失、任务不会因 API 进程重启丢失。

## Volume 与网络

- `postgres-data` 保存 PostgreSQL 数据。
- `redis-data` 保存 Redis AOF 数据。
- 初始化 SQL 只读挂载到 `/docker-entrypoint-initdb.d/001-init.sql`。
- 容器通过服务名 `db:5432`、`redis:6379` 通信。
- 只有 API 映射到宿主机 `8001`，数据库和 Redis 不暴露宿主机端口。

不要在需要保留数据时运行：

```powershell
docker compose down -v
```

## 日志排查

```powershell
docker compose logs api
docker compose logs db
docker compose logs redis
docker compose logs dispatcher
```

| 现象 | 优先检查 | 正确修复方向 |
|---|---|---|
| API 存活但 `/ready` 503 | db/redis health 与连接 URL | 使用服务名，不使用容器内 `localhost` |
| task 一直 `pending` | dispatcher 状态和日志 | 恢复 dispatcher，不手工改 task 状态 |
| Redis 暂时不可用 | dispatcher 日志、outbox claim | 允许 claim 释放或过期后重试 |
| API 重启后 task 消失 | 是否误用内存模式 | Compose 设置 `P03_BACKEND=postgres` |
| 数据全部消失 | 是否执行 `down -v` | 使用 named volume 并区分清理命令 |

## 自动参考验证

```powershell
.\scripts\verify_compose.ps1
```

脚本覆盖幂等提交、正常完成、确定性失败、dispatcher 积压恢复、worker 租约恢复、API 重启持久化和重复消息去重。

## 参考验收证据

- [x] 五服务 Compose 从空卷构建并全部 healthy。
- [x] API 使用 `db`、`redis` 服务名连接依赖。
- [x] task/outbox 在 PostgreSQL 同事务写入。
- [x] dispatcher 停止期间任务和 outbox 不丢失。
- [x] API 重启后任务仍可查询。
- [x] PostgreSQL/Redis 使用 named volume，镜像和 Python 基线已固定。

## 学习者验收

- [ ] 能画出 task/outbox/Redis 的所有权关系。
- [ ] 能亲自从空卷启动并保存 `docker compose ps` 证据。
- [ ] 能解释为什么 API 不直接双写 PostgreSQL 与 Redis。
- [ ] 能完成一次 dispatcher 停机恢复并记录状态变化。
- [ ] 能区分 `/health`、`/ready` 和任务闭环验证。

## 边界提醒

本实验使用开发密码和 mock workload，不提供生产级认证、TLS、Secret 管理、高可用 PostgreSQL/Redis 或灾备方案。
