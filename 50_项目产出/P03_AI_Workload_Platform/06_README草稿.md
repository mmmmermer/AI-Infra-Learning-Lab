# P03 README 草稿

## 当前可运行入口

`p03_service/` 是 v0.3.1 可执行参考实现，包含两种运行模式和两类 workload：

- 默认 `memory`：单进程教学模式，便于阅读状态机并运行单元测试。
- Compose `postgres`：PostgreSQL、Redis、API、outbox dispatcher、独立 worker。
- mock workload：用于状态机、故障和压测。
- `rag_retrieval`：固定语料 BM25、租户隔离、权限前置过滤和来源持久化。

```powershell
cd p03_service
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
```

真实多服务参考验证：

```powershell
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8001/ready
.\scripts\verify_compose.ps1
```

## 项目简介

P03 AI Workload Platform 是面向 RAG、Agent 和模拟推理请求的最小任务平台。当前版本训练的是可靠任务生命周期，不是模型效果：

```text
API 事务写 task + outbox
-> dispatcher 发布 task_id
-> Redis 至少一次投递
-> worker 用数据库 CAS 认领
-> mock workload 执行
-> 结果或错误持久化
-> API 查询状态和基础 metrics
```

## v0.3.1 已实现

- `POST /tasks` 幂等创建任务。
- `GET /tasks/{task_id}` 查询持久化状态。
- `GET /health` 进程存活检查，`GET /ready` 依赖就绪检查。
- PostgreSQL task/outbox 同事务写入。
- 带租约的 outbox dispatcher 和 Redis task-id 队列。
- 独立 worker、owner-checked CAS、确定性失败记录。
- worker 中断后的租约过期恢复。
- API 重启后的数据持久性和重复 Redis 消息去重。
- 当前完整套件 27 tests、真实 Compose 故障脚本和 1/2/4 worker 对照脚本；其中 3 项验证 fixed-replay sender 调度、校验与导出语义，不是服务压测。
- bearer token 到 server-owned principal 的本地 reference 映射。
- tenant/user scoped 幂等与任务查询。
- 固定 golden queries、公开/私密/跨租户/空语料 RAG 检索路径。
- 500ms 队列时序、worker 容器 CPU/内存时序和 1/2/4 worker × 3 次随机化
  本机 reference，含 95% Student t 区间。

## 当前边界

当前 worker 已执行真实 BM25 检索，但 answer 是确定性 extractive assembly，
不是 LLM generation。尚未实现：

- 文档导入、向量检索、引用质量评估和生产权限系统。
- Agent 多步骤工作流与人工审批。
- Prometheus Histogram、tracing、学习者长时/真实 workload 压测报告。
- 真实推理服务、GPU 调度，以及 Kubernetes 自动扩缩容和生产化部署。
- 生产级鉴权、密钥管理、TLS 和外部副作用幂等。

本地 Compose 密码只用于教学环境。参考实现验证不等于学习者已经复现。

## 实验连接

- E06：事务 outbox、幂等、状态 CAS、租约恢复。
- E07：Dockerfile、Compose、健康检查、日志和故障排查。
- E08：后续基于当前 API/worker 闭环补负载生成、分位数和利用率。

实验记录见：

- [[50_项目产出/P03_AI_Workload_Platform/04_实验记录/00_实验索引|P03 实验记录索引]]

## 后续计划

1. 用 `rag_retrieval` 而不是 mock workload 运行 E08，并补 warm-up/长时规则。
2. 增加外部副作用幂等和长任务 heartbeat。
3. 为 RAG workload 补 corpus lifecycle、generation 和质量评测。
4. 学习者复现现有 kind 功能闭环，再补 metrics-server、HPA/KEDA、持久化和生产安全边界。
