# E09-03 模拟 worker pod 扩缩容

> 状态（2026-07-18）：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 pending`。P03 v0.3.1 已在 kind 完成 PostgreSQL/Redis/API/dispatcher/worker 部署和 1/2/4 worker 手工扩缩容；每组 24 tasks、0 failures，并持久化 1/2/4 个不同 worker ID。该单轮结果不是性能结论。

## 为什么不能扩 API 代替扩 worker

把现有 API Deployment 从 1 个副本扩到 4 个，不等于得到 4 个共享队列 worker：

```text
api replicas -> 接收和查询请求
worker replicas -> 从共享 Redis 消费 task_id
PostgreSQL -> 唯一任务事实源
```

E09-02 的教学 manifest 使用内存模式，因此不能扩 API。E09-03 必须切换到 `P03_BACKEND=postgres`，让 API、dispatcher 和所有 worker 连接同一个 PostgreSQL/Redis，再只改变 worker Deployment 的副本数。

## 升格前置条件

P03 v0.3.1 reference 对前置条件的满足情况：

1. [x] API、dispatcher、worker 有不同启动命令。
2. [x] 任务状态位于 PostgreSQL。
3. [x] Redis 传递 `task_id`。
4. [x] worker 使用原子 claim/CAS，重复投递已验证。
5. [x] metrics 区分 broker backlog、状态、active task、成功、失败和重试。
6. [x] Locust 固定 mock workload 和空库 smoke 脚本可重放。
7. [x] kind 中的 PostgreSQL/Redis/API/dispatcher/worker 已部署并验证。
8. [x] Compose reference 已有 claimed-task wall time utilization。
9. [ ] kind reference 尚未安装 metrics-server；Pod CPU/内存仍未纳入本页。

M06 的 SQLite 实现用于解释语义；E09-03 使用 P03 v0.3.1 的 PostgreSQL repository，没有把 SQLite 文件挂给多个 Pod。

## Worker Deployment 草稿

下面 manifest 假设集群中已经存在可访问的 `p03-db:5432` 和 `p03-redis:6379`。本地实验可以部署教学用 StatefulSet/Service，真实环境应改用受控数据库和 Secret 管理。

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: p03-runtime
data:
  P03_BACKEND: postgres
  REDIS_URL: redis://p03-redis:6379/0
  REDIS_QUEUE_KEY: p03:tasks:stream:v1
  WORKER_LEASE_SECONDS: "8"
---
apiVersion: v1
kind: Secret
metadata:
  name: p03-database
type: Opaque
stringData:
  DATABASE_URL: postgresql://p03:replace-me@p03-db:5432/p03
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: p03-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: p03-worker
  template:
    metadata:
      labels:
        app.kubernetes.io/name: p03-worker
    spec:
      containers:
        - name: worker
          image: p03-service:0.3.1
          imagePullPolicy: IfNotPresent
          command: ["python", "-m", "app.worker_service"]
          envFrom:
            - configMapRef:
                name: p03-runtime
            - secretRef:
                name: p03-database
          readinessProbe:
            exec:
              command: ["python", "-m", "app.dependency_check"]
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: "1"
              memory: 512Mi
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
```

dispatcher 应使用同一镜像和配置，但命令是 `python -m app.dispatcher`，第一轮固定 `replicas: 1`。

## 手工扩容实验

前置条件满足后，先做手工副本对比，不先上 HPA：

```powershell
kubectl scale deployment p03-worker --replicas=1
kubectl rollout status deployment/p03-worker
# 运行固定 workload，保存原始请求和指标

kubectl scale deployment p03-worker --replicas=2
# 用相同 workload、seed 和到达时间重跑

kubectl scale deployment p03-worker --replicas=4
# 再次重跑
```

每组至少记录：

| replicas | request_count | queue_wait_p50 | queue_wait_p95 | queue_wait_p99 | throughput | error_rate | worker_utilization | test_duration |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |
| 4 |  |  |  |  |  |  |  |  |

改变副本数时不能同时改变请求分布、模型、数据库、调度策略或机器资源，否则无法归因。

## 已执行 Functional Reference

`kind_reference/scripts/verify_kind.ps1` 对每个副本组提交 24 个固定
`mock_rag sleep_ms=200` tasks，并查询 PostgreSQL 中不同 `worker_id` 数量：

| replicas | ready | tasks | failures | distinct worker IDs | queue P95 | queue P99 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 24 | 0 | 1 | 5608.94 ms | 5754.54 ms |
| 2 | 2 | 24 | 0 | 2 | 2055.22 ms | 2104.46 ms |
| 4 | 4 | 24 | 0 | 4 | 805.13 ms | 835.58 ms |

这证明副本 rollout、共享 Redis/PostgreSQL 和多 worker 实际消费成立。每组只有一次，
且 kind 与 Compose 的启动/资源环境不同；不得把延迟数值写成稳定扩展规律。

## HPA 的正确边界

CPU HPA 需要 Metrics Server；按业务队列长度扩容通常还需要自定义指标适配器或 KEDA。二者不是同一件事。

```powershell
kubectl top pods
kubectl get apiservice v1beta1.metrics.k8s.io
```

如果这些命令无有效指标，HPA 实验尚不具备前提。

一个 CPU HPA 示例只能验证资源指标扩容，不证明 queue-driven scaling：

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: p03-worker
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: p03-worker
  minReplicas: 1
  maxReplicas: 4
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
```

## 失败诊断

| 现象 | 可能原因 |
|---|---|
| 副本增加但吞吐不变 | 数据库/队列/下游模型是瓶颈 |
| 任务重复执行 | claim、幂等或 lease 不成立 |
| 查询偶发 404 | API 仍使用 Pod 本地状态 |
| HPA 显示 unknown | Metrics Server 或 requests 配置缺失 |
| queue length 降低但 P99 变差 | 下游竞争、批处理或数据库争用 |

## 学习者验收

Reference 已验证共享依赖、1/2/4 replicas 和不同 worker IDs；下列项目仍要求
学习者亲手复现和解释。

- [ ] 能解释为什么 E09-02 的内存 API 不能水平扩容。
- [ ] 能验证所有 worker 连接同一个 PostgreSQL 和 Redis。
- [ ] 能区分手工 replicas、CPU HPA 和 queue-driven scaling。
- [ ] 能设计只改变 worker 副本数的可归因实验。

## 边界

当前页面已有实际 kind 功能性扩缩容 reference，但仍缺 metrics-server/HPA、
queue-driven scaling、重复 Kubernetes 实验、长期存储和生产安全，不是生产扩缩容结果。
