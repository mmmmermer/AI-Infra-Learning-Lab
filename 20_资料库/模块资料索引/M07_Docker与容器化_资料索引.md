# M07 Docker 与容器化资料索引

## 当前策略

Docker 资料服务于 P03 本地一键启动和可复现交付，不做运维大而全。

第一轮资料使用顺序：

```text
M07 学习地图
-> M07 适配教材
-> 本资料索引按需查官方资料
-> E07 实验
-> P03 compose 一键启动
```

| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 M07 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| Docker Get Started | https://docs.docker.com/get-started/ | 官方文档 | 必读 | 入门 | 理解 image、container、Dockerfile | 教材第 1-2 章；E07-01 |
| Dockerfile reference | https://docs.docker.com/reference/dockerfile/ | 官方文档 | 查阅 | Dockerfile | 查 FROM、WORKDIR、COPY、RUN、CMD、EXPOSE | 教材第 4 章；E07-01 |
| Docker Compose Docs | https://docs.docker.com/compose/ | 官方文档 | 必读 | 多服务启动 | 查 services、ports、volumes、environment、depends_on | 教材第 5-8 章；E07-02 |
| Compose Getting Started | https://docs.docker.com/compose/gettingstarted/ | 官方文档 | 必读 | Compose 最小实践 | 对照最小多服务 compose | E07-02 / P03 |

## 和教材章节的对应关系

| 教材章节 | 优先资料 | 使用方式 |
|---|---|---|
| 第 1-2 章：为什么容器化 / image 和 container | Docker Get Started | 看概念，不深挖底层实现 |
| 第 4 章：Dockerfile | Dockerfile reference | 查指令含义 |
| 第 5 章：volume | Docker Compose Docs | 查 volumes 写法 |
| 第 6 章：network | Docker Compose Docs | 查服务名、ports |
| 第 7 章：compose 串起 P03 | Docker Compose Docs、Compose Getting Started | 转化成 P03 compose |
| 第 8-9 章：环境变量和日志 | Docker Compose Docs | 查 env_file、logs |

## 对应实验

- [[40_实验练习/E07_Docker实验/E07_Docker实验_索引|E07 Docker 实验索引]]
- [[40_实验练习/E07_Docker实验/E07-01 最小 FastAPI Dockerfile|E07-01 最小 FastAPI Dockerfile]]
- [[40_实验练习/E07_Docker实验/E07-02 docker compose 串联 API + db + redis|E07-02 docker compose 串联 API + db + redis]]
- [[40_实验练习/E07_Docker实验/E07-03 worker 服务与日志排查|E07-03 worker 服务与日志排查]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 RAG Agent Service]]

## 不做

- 不先追求镜像极限优化
- 不先学复杂生产部署
- 不先碰 Kubernetes
- 不做服务网格
- 不做复杂 CI/CD
- 不做生产级安全加固

## 资料转化检查

- [ ] 每条必读资料至少对应一个教材章节。
- [ ] 每条必读资料至少能转化为一个 E07 实验观察点。
- [ ] P03 能接收资料转化出的 Dockerfile、compose、env 或排查记录。
- [ ] 没有把资料索引写成泛泛链接台账。
- [ ] 没有虚构资料来源。
