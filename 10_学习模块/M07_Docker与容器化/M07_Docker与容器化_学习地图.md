# M07 Docker 与容器化学习地图

## 怎么读这个模块

把 M07 当成“让 P03 在你电脑上稳定启动”的工程说明书，不要当成 Docker 全家桶教程。

阅读主线是：写 Dockerfile，准备环境变量，compose 启动 api/db/redis/worker，volume 保存数据，network 让服务互通，logs 用来排错。

每学一个概念，都要能回答：它在 `docker compose up --build` 这条启动链路里解决了什么问题？

## 在总路线中的位置

M07 负责把 M02 的 FastAPI、M03 的 RAG worker、M06 的数据库/Redis/异步任务服务，整理成可以稳定启动、复现和交付的本地多服务系统。

在 P03 中，它承接这条链路：

```text
FastAPI API
-> PostgreSQL / SQLite
-> Redis
-> worker
-> docker compose 一键启动
```

正式入口只保留：

1. [[M07_Docker与容器化_学习地图|M07 Docker 与容器化学习地图]]
2. [[M07_Docker与容器化_适配教材|M07 Docker 与容器化适配教材]]

## 要解决的问题

- 如何让系统一键启动？
- 如何隔离依赖？
- 如何把 FastAPI、数据库、Redis、worker 放进同一个 compose？
- volume、network、环境变量和日志分别解决什么问题？
- 容器启动、镜像大小和日志排查如何影响 AI 服务体验？

## 学习目标

- [ ] 能解释 image、container、Dockerfile、volume、network、compose。
- [ ] 能写最小 FastAPI Dockerfile。
- [ ] 能用 docker compose 启动 api、db、redis、worker。
- [ ] 能用环境变量配置数据库和 Redis 地址。
- [ ] 能用 logs 排查 API、worker、db、redis 启动问题。
- [ ] 能说明 M07 如何承接 M02/M03/M06 并服务 P03。

## 核心内容

| 内容 | 学到什么程度 | 落地点 |
|---|---|---|
| image / container | 能解释模板和运行实例的区别 | E07-01 |
| Dockerfile | 能把 FastAPI 服务打成镜像 | E07-01 |
| volume | 能保留数据库数据和上传文件 | E07-02 |
| network | 能用服务名连接 db/redis | E07-02 |
| docker compose | 能一键启动 api/db/redis/worker | P03 |
| 环境变量 | 能写 `.env.example` 和 `env_file` | P03 |
| 日志排查 | 能用 compose logs 定位问题 | E07-03 |

## 对应资料

- [[20_资料库/模块资料索引/M07_Docker与容器化_资料索引|M07 Docker 与容器化资料索引]]
- [Docker Get Started](https://docs.docker.com/get-started/)
- [Dockerfile reference](https://docs.docker.com/reference/dockerfile/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Compose Getting Started](https://docs.docker.com/compose/gettingstarted/)

## 对应知识卡片

- [[Dockerfile]]
- [[docker compose]]
- [[容器网络]]
- [[容器冷启动]]

## 对应实验

- [[40_实验练习/E07_Docker实验/E07_Docker实验_索引|E07 Docker 实验索引]]
- [[40_实验练习/E07_Docker实验/E07-01 最小 FastAPI Dockerfile|E07-01 最小 FastAPI Dockerfile]]
- [[40_实验练习/E07_Docker实验/E07-02 docker compose 串联 API + db + redis|E07-02 docker compose 串联 API + db + redis]]
- [[40_实验练习/E07_Docker实验/E07-03 worker 服务与日志排查|E07-03 worker 服务与日志排查]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 RAG Agent Service]]

## 推荐学习顺序

1. 读 [[M07_Docker与容器化_适配教材|M07 适配教材]] 第 1-3 章，理解容器化服务 P03 复现。
2. 完成 E07-01：最小 FastAPI Dockerfile。
3. 完成 E07-02：compose 启动 api、db、redis。
4. 写 `.env.example`，统一 DATABASE_URL、REDIS_URL、API_PORT。
5. 用 logs 排查启动错误。
6. 完成 E07-03：worker 服务与日志排查。

## 检查标准

- [ ] 能写 Dockerfile。
- [ ] 能用 compose 启动多个服务。
- [ ] 能配置 volume、network 和环境变量。
- [ ] 能排查容器日志。
- [ ] 能解释镜像和启动时间对服务的影响。
- [ ] 能让 P03 最小服务组一键启动。

## 暂时不深入

- 不做 Kubernetes。
- 不做服务网格。
- 不做复杂 CI/CD。
- 不做生产级安全加固。
- 不做 Docker 底层源码。
