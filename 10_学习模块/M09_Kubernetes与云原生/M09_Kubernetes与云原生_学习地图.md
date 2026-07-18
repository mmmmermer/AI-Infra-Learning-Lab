# M09 Kubernetes 与云原生学习地图

## 怎么读这个模块

M09 是长期进阶模块，第一遍只读“Compose 项目将来如何搬到 Kubernetes”，不要读成 K8s 大书。

阅读主线是：P03 的 api/worker/config/入口，在 Kubernetes 里分别对应 Pod、Deployment、Service、ConfigMap、Secret、Ingress。Scheduler 部分只做和 M05 的类比。

当前不需要写复杂集群方案，也不需要读源码。

## 在总路线中的位置

M09 是长期进阶模块，用来理解 P03 未来如何从 Docker Compose 本地复现，逐步迁移到 Kubernetes 和云原生运行环境。

它不是当前阶段的主战场。当前重点仍是 M02/M03/M04/M05/M06/M07/M08 把 P03 的 API、RAG、Agent、队列、数据库、容器化和监控闭环做扎实。

M09 的主线是：

```text
M07 Docker Compose
-> P03 api/db/redis/worker
-> Kubernetes Pod / Deployment / Service
-> worker 扩缩容
-> M05 调度概念映射
-> 后续 Kueue / Volcano / AI workload 调度
```

## 要解决的问题

- Docker Compose 项目未来如何迁移到 Kubernetes？
- Pod、Deployment、Service、ConfigMap、Secret、Ingress 分别解决什么问题？
- Job、CronJob 和长期 worker 有什么区别？
- HPA 如何对应 worker 扩缩容？
- Kubernetes Scheduler 和 M05 的 Scheduler 有什么相似和不同？
- queue、admission、quota 如何连接调度实验？

## 学习目标

- [ ] 能解释 Pod、Deployment、Service、ConfigMap、Secret、Ingress、Job、CronJob、HPA、Scheduler 的基础作用。
- [ ] 能把 P03 的 api、worker、配置、HTTP 入口映射到 K8s 对象。
- [ ] 能说明从 Compose 到 K8s 的分阶段迁移路线。
- [ ] 能把 M05 的 Task/Worker/Queue/Scheduler 类比到 Pod/Node/queue/Scheduler。
- [ ] 能区分 P03 业务任务调度和 Kubernetes Pod 资源调度。
- [ ] 能说明为什么本模块暂时不读源码、不做 CRD/operator、不深入服务网格。

## 核心内容

| 内容 | 学到什么程度 | 对应出口 |
|---|---|---|
| Pod | 最小运行/调度单元 | E09-01 |
| Deployment | 管理 API/worker 副本 | E09-02 |
| Service | 给 Pod 稳定访问入口 | E09-02 |
| ConfigMap | 非敏感配置 | P03 迁移路线 |
| Secret | 敏感配置对象 | P03 迁移路线 |
| Ingress | HTTP 入口 | E09-02 |
| Job | 一次性任务 | E09-03 |
| CronJob | 定时任务 | E09-03 |
| HPA | 水平扩缩容 | E09-03 |
| Scheduler | Pod 到 Node 的调度 | M05 映射 |

## 对应资料

- [[20_资料库/模块资料索引/M09_Kubernetes与云原生_资料索引|M09 Kubernetes 与云原生资料索引]]
- [Kubernetes Basics](https://kubernetes.io/docs/tutorials/kubernetes-basics/)
- [Kubernetes Scheduler](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)
- [Kueue Documentation](https://kueue.sigs.k8s.io/docs/)

## 对应知识卡片

- [[Pod]]
- [[Deployment]]
- [[Service]]
- [[ConfigMap]]
- [[Secret]]
- [[Ingress]]
- [[Job]]
- [[CronJob]]
- [[HPA]]
- [[Kubernetes Scheduler]]
- [[Kueue]]

## 对应实验

- [[40_实验练习/E09_K8s实验/E09_K8s实验_索引|E09 K8s 实验索引]]
- [[E09-01 kind 本地集群]]
- [[E09-02 部署 FastAPI 服务]]
- [[E09-03 模拟 worker pod 扩缩容]]
- [[E09-04 Kueue 概念实验]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 推荐学习顺序

1. 先读 [[M09_Kubernetes与云原生_适配教材|M09 适配教材]] 第 1 章，确认 M09 是长期进阶导论。
2. 读第 2-5 章，理解 Pod、Deployment、Service、Ingress、ConfigMap、Secret。
3. 读第 6-7 章，理解 Job、CronJob 和 HPA。
4. 读第 8 章，把 M05 调度模型映射到 Kubernetes。
5. 读第 9 章，写出 P03 从 Compose 到 K8s 的最小迁移路线。
6. 后续再细化 E09 实验页。

## 检查标准

- [ ] 能部署或讲清一个服务到本地 K8s 的最小过程。
- [ ] 能解释 Pod、Deployment、Service、Ingress 的关系。
- [ ] 能解释 ConfigMap 和 Secret 的区别。
- [ ] 能理解 HPA 的作用。
- [ ] 能说明 AI workload 调度和普通 Web 服务部署的不同。
- [ ] 能把 M05 的 Task/Worker/Queue/Scheduler 映射到 Kubernetes 概念。

## 暂时不深入

- 不读 Kubernetes Scheduler 源码。
- 不实现自定义 Scheduler。
- 不讲复杂 CRD/operator。
- 不深入服务网格。
- 不做生产集群运维。
- 不展开 Kueue/Volcano 的完整安装和生产用法。
