# M09 Kubernetes 与云原生资料索引

## 当前策略

Kubernetes 资料属于长期进阶。第一轮只服务于两个目标：

1. 理解 P03 如何从 Docker Compose 迁移到 Kubernetes。
2. 理解 Kubernetes 调度概念如何映射到 M05 的 Task/Worker/Queue/Scheduler。

资料不是云原生收藏夹，不进入 Scheduler 源码、CRD/operator、服务网格或生产集群运维。

## 资料闭环

```text
M09 学习地图
-> M09 导论型适配教材
-> 本资料索引按需查官方资料
-> E09 K8s 实验
-> P03 未来迁移路线
```

## 资料列表

| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 M09 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| Kubernetes Basics | https://kubernetes.io/docs/tutorials/kubernetes-basics/ | 官方文档 | 必读 | 入门 | 建立 Pod、Service、Deployment 基础 | 第 1-4 章 |
| Kubernetes Pods | https://kubernetes.io/docs/concepts/workloads/pods/ | 官方文档 | 必读 | Pod | 查 Pod 定义和最小概念 | 第 2 章 |
| Kubernetes Deployments | https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ | 官方文档 | 必读 | Deployment | 查副本、滚动更新和服务管理 | 第 3 章 |
| Kubernetes Services | https://kubernetes.io/docs/concepts/services-networking/service/ | 官方文档 | 必读 | 网络入口 | 查 Service 如何稳定访问 Pod | 第 4 章 |
| ConfigMaps | https://kubernetes.io/docs/concepts/configuration/configmap/ | 官方文档 | 查阅 | 配置 | 查非敏感配置对象 | 第 5 章 |
| Secrets | https://kubernetes.io/docs/concepts/configuration/secret/ | 官方文档 | 查阅 | 配置 | 查敏感配置对象 | 第 5 章 |
| Ingress | https://kubernetes.io/docs/concepts/services-networking/ingress/ | 官方文档 | 查阅 | HTTP 入口 | 理解 Ingress 位置 | 第 4 章 |
| Job | https://kubernetes.io/docs/concepts/workloads/controllers/job/ | 官方文档 | 查阅 | batch | 理解一次性任务 | 第 6 章 |
| CronJob | https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/ | 官方文档 | 查阅 | 定时任务 | 理解定时任务 | 第 6 章 |
| HPA Docs | https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/ | 官方文档 | 选读 | 扩缩容 | 理解 worker 副本变化 | 第 7 章 |
| Kubernetes Scheduler | https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/ | 官方文档 | 必读 | 调度概念 | 只读概念，不读源码 | 第 8 章 |
| kind Quick Start | https://kind.sigs.k8s.io/docs/user/quick-start/ | 官方文档 | 查阅 | 本地实验 | 后续 E09-01 使用 | E09-01 |
| Kueue Documentation | https://kueue.sigs.k8s.io/docs/ | 官方文档 | 选读 | batch queue | 只理解 queue/admission/quota | E09-04 |
| Volcano Docs | https://volcano.sh/docs/home/introduction/ | 官方文档 | 暂缓 | AI/HPC batch | 后续理解 batch scheduling | 进阶 |
| CNCF Landscape | https://landscape.cncf.io/ | 官方资料 | 查阅 | 生态地图 | 只看生态位置，不展开学习 | 进阶 |

## 教材章节对应

| 教材章节 | 主要资料 | 使用方式 |
|---|---|---|
| 第 1 章：Kubernetes 解决什么问题 | Kubernetes Basics | 建立 Compose 到 K8s 的位置 |
| 第 2 章：Pod | Kubernetes Pods | 理解最小调度单元 |
| 第 3 章：Deployment | Deployments | 理解 api/worker 副本 |
| 第 4 章：Service 和 Ingress | Services / Ingress | 理解访问入口 |
| 第 5 章：ConfigMap 和 Secret | ConfigMaps / Secrets | 理解配置迁移 |
| 第 6 章：Job 和 CronJob | Job / CronJob | 理解一次性和定时任务 |
| 第 7 章：HPA | HPA Docs | 理解 worker 扩缩容 |
| 第 8 章：Scheduler | Kubernetes Scheduler / Kueue | 映射 M05 调度模型 |

## 对应实验

- [[40_实验练习/E09_K8s实验/E09_K8s实验_索引|E09 K8s 实验索引]]
- [[E09-01 kind 本地集群]]
- [[E09-02 部署 FastAPI 服务]]
- [[E09-03 模拟 worker pod 扩缩容]]
- [[E09-04 Kueue 概念实验]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 和相关模块的关系

- M05：提供 Task/Worker/Queue/Scheduler 的调度直觉。
- M07：提供 Dockerfile 和 compose 基础，是进入 K8s 的前置。
- M08：提供 queue_wait、worker utilization、P95/P99 等扩缩容观察指标。
- P03：未来迁移对象是 api、worker、配置、入口和扩缩容。

## 不做

- 不读 Kubernetes Scheduler 源码。
- 不实现自定义 Scheduler。
- 不讲复杂 CRD/operator。
- 不深入服务网格。
- 不做生产集群运维。
- 不把云原生生态图当学习清单逐个啃。

## 转化检查

- [ ] 每条必读资料能转化为教材章节、E09 实验或 P03 迁移对象。
- [ ] 资料没有引导到 Scheduler 源码和生产运维发散。
- [ ] M09 始终保持长期进阶导论定位。
