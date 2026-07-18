# E07 Docker 实验索引

> 状态（2026-07-10）：E07-01 至 E07-03 均已有经过实际验证的参考实现。P03 v0.2 Compose 已包含 PostgreSQL、Redis、API、transactional-outbox dispatcher 和独立 worker，并通过正常路径、dispatcher 积压、worker 租约恢复、API 重启和重复投递检查。学习者复现状态仍保持未完成。

## 定位

E07 用于把 M07 的教材内容落到可复现的容器化实验上。

它验证三件关键工程问题：

1. FastAPI 服务是否能被 Dockerfile 稳定构建和启动。
2. API、数据库、Redis、worker 是否能被 compose 串起来。
3. 出错时能否通过 logs、ps、env 和服务名定位问题。

## 推荐实验

| 实验 | 对应教材章节 | 观察目标 | 输出记录 |
|---|---|---|---|
| [[40_实验练习/E07_Docker实验/E07-01 最小 FastAPI Dockerfile|E07-01 最小 FastAPI Dockerfile]] | 第 2-4 章：image/container/Dockerfile | API 镜像是否能构建，容器是否能访问 | Dockerfile、build time、image size、API logs |
| [[40_实验练习/E07_Docker实验/E07-02 docker compose 串联 API + db + redis|E07-02 docker compose 串联 API + db + redis]] | 第 5-8 章：volume/network/compose/env | api、db、redis 是否能互通，`POST /tasks` 是否能创建任务 | compose.yml、service status、env、volume、task_id |
| [[40_实验练习/E07_Docker实验/E07-03 worker 服务与日志排查|E07-03 worker 服务与日志排查]] | 第 7-9 章：worker、compose、logs | worker 是否能消费任务并回写状态 | worker logs、status flow、error log、fix |

## 总练习路线

```text
FastAPI 容器化
-> 配置环境变量
-> 加入数据库和 Redis
-> 加入 worker
-> compose 一键启动
-> logs 排查错误
```

第一轮不要先追求 Kubernetes、服务网格、复杂 CI/CD 或生产级安全加固。目标是让 P03 最小服务组能在本地稳定复现。

## 统一记录字段

```text
service_name
image_name
container_status
build_time
image_size
startup_time
ports
volumes
env_file
log_excerpt
error_type
fix_notes
```

## 分层贯通目标

当前参考实现已验证：

```text
docker compose up --build -d
-> api/db/redis/dispatcher/worker healthy
-> POST /tasks
-> dispatcher 发布 task_id
-> 独立 worker 自动执行
-> GET /tasks/{task_id}
-> GET /metrics
```

闭环使用 PostgreSQL 作为唯一任务事实源，Redis 只传递 `task_id`。参考脚本还实际停启 dispatcher/worker/API 并注入重复 Redis 消息，不再依赖进程内共享状态。

第一轮允许 RAG 使用 `RAG_MODE=mock`。本阶段重点是容器化和服务互通，不是 RAG 质量优化。

## 参考脱敏合规 AI 案例 compose 的方式

脱敏合规 AI 案例工程中的 `docker-compose.yml` 可以作为结构参考：

- postgres 和 redis 拆成独立服务。
- 数据服务使用 named volume。
- postgres/redis 配置 healthcheck。

但 P03 第一轮不能直接复制成脱敏合规 AI 案例的 compose：

- qdrant 暂时是可选向量库，不是 E07 第一轮必需服务。
- minio 暂时是对象存储进阶，不是 P03 最小启动必需服务。
- 项目名、端口、初始化脚本和业务服务都要按 P03 自己的 API/worker 设计。

## 对应模块

- [[10_学习模块/M07_Docker与容器化/M07_Docker与容器化_学习地图|M07 Docker 与容器化学习地图]]
- [[10_学习模块/M07_Docker与容器化/M07_Docker与容器化_适配教材|M07 Docker 与容器化适配教材]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 验收标准

- [ ] 能解释每个实验对应 M07 教材哪一章。
- [x] 参考实现能构建 API 镜像并通过健康检查。
- [x] 参考实现能用 compose 启动 api、db、redis、dispatcher、worker。
- [x] 参考实现能用服务名连接 db/redis。
- [ ] 能用 logs 排查至少三个常见错误。
- [ ] 能说明实验结果如何影响 P03 的一键启动和 README。
