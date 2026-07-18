# M07 Docker 与容器化适配教材

<!-- textbook-content: default=instructional -->

## 模块入口

| 项目 | 开始前应知道的边界 |
|---|---|
| 目标读者 | 已有一个可启动的 Python/FastAPI 服务，希望把 API、数据库、Redis、dispatcher 和 worker 组成可复现本地环境的学习者 |
| 先修知识 | 命令行、端口和环境变量基础；能读懂 Dockerfile 中的工作目录、复制与启动命令；了解 M06 的 task/outbox/worker 职责 |
| 可执行环境检查 | 运行 `docker version`、`docker compose version`、`docker info` 和 `git --version`。命令必须能连接 Docker daemon；只有客户端版本输出不足以开始 compose 实验 |
| 学习产物 | Dockerfile、`.dockerignore`、`.env.example`、Compose 配置、`docker compose ps`/logs 证据和故障排查记录；真实密钥不得进入仓库 |
| 完成口径 | P03/E07 的 verified reference 说明参考栈曾通过构建与闭环检查，不表示学习者已复现。学习者完成状态必须关联自己的镜像、容器状态、请求结果和日志 |
| 预计学习时间与退出点 | 首轮约 6-10 小时；第 4 章后可先完成单服务镜像，第 9 章后再做完整 Compose 与故障注入，避免构建、网络和业务错误同时出现 |
| 版本边界 | 当前 reference 是 P03 v0.3.1：Python 3.13.2 slim-bookworm、PostgreSQL 17.5-alpine、Redis 8.0.3-alpine，镜像按 digest 固定。Docker Engine/Compose 未声明通用最低版本，升级时先用 `docker compose config --quiet` 和 reference smoke 复核 |

## 内容类型说明

| 范围 | 类型 | 阅读承诺 |
|---|---|---|
| 第 1-6、8-9 章 | `instructional` | 用于第一次建立 image/container、Dockerfile、volume、network、环境变量与日志排查能力 |
| 第 7 章及项目贯通案例 | `design-note` | 正文中的四服务简化 compose 是教学拓扑，不是 P03 v0.3.1 的五服务 reference 契约；实际运行应以 `p03_service/compose.yaml` 为准 |
| 第 10 章 | `appendix` | 给出学习顺序、范围和退出点 |
| 第 11 章 | `reference` | 用于查阅 Docker 官方资料，不替代正文教学 |

## 编写说明

M07 的目标不是学习 Docker 全家桶，而是让前面做出的 API、RAG、数据库、Redis 和 worker 能稳定启动、复现和交付。

在 P03 里，M07 承接的是这条工程线：

```text
M02 FastAPI
-> M03 RAG worker
-> M06 数据库 / Redis / 异步任务
-> M07 Dockerfile / compose 一键启动
-> M08 监控压测
-> M09 Kubernetes
```

没有 M07，P03 很容易停留在“我本机能跑”的阶段。有了 M07，项目才开始具备可复现性：

```text
别人拉代码 -> 配置 .env -> docker compose up -> API / DB / Redis / Worker 一起启动
```

本教材主要连接：

- [[10_学习模块/M07_Docker与容器化/M07_Docker与容器化_学习地图|M07 Docker 与容器化学习地图]]
- [[20_资料库/模块资料索引/M07_Docker与容器化_资料索引|M07 Docker 与容器化资料索引]]
- [[40_实验练习/E07_Docker实验/E07_Docker实验_索引|E07 Docker 实验索引]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[10_学习模块/M02_后端API与服务化/M02_后端API与服务化_学习地图|M02 后端 API 与服务化学习地图]]
- [[10_学习模块/M03_RAG工程/M03_RAG工程_学习地图|M03 RAG 工程学习地图]]
- [[10_学习模块/M06_数据库缓存与异步任务/M06_数据库缓存与异步任务_学习地图|M06 数据库缓存与异步任务学习地图]]

推荐资料以 M07 资料索引为准，第一轮优先查阅：

- [Docker Get Started](https://docs.docker.com/get-started/)
- [Dockerfile reference](https://docs.docker.com/reference/dockerfile/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Compose Getting Started](https://docs.docker.com/compose/gettingstarted/)

## 第一轮学习边界

Docker 很容易扩成部署、运维、云原生、安全、CI/CD 的大杂烩。当前 M07 只服务 P03 的本地可复现交付。

| 内容 | 第一轮必须掌握 | 第一轮暂不深入 | 为什么这样划边界 |
|---|---|---|---|
| image / container | 知道镜像是模板，容器是运行实例 | 不研究底层 namespace/cgroup 实现 | 先能解释 Docker 在项目交付中做什么 |
| Dockerfile | 能把 FastAPI 服务打成镜像 | 不做复杂多阶段极限优化 | P03 先要能稳定构建 |
| volume | 会让数据库数据、上传文件、日志不随容器删除而丢 | 不做复杂存储驱动和备份体系 | M06 的数据必须可保留 |
| network | 会让 api、db、redis、worker 用服务名互相访问 | 不深入容器网络底层 | compose 服务互通是 P03 关键 |
| docker compose | 能一键启动 API、DB、Redis、worker | 不做 Kubernetes 和 Swarm | 第一轮只需本地多服务编排 |
| 环境变量 | 会用 `.env` 配置数据库 URL、Redis URL、模型 key | 不做复杂密钥管理平台 | 项目不能把配置写死进代码 |
| 日志 | 会用 `docker compose logs` 排查启动和运行错误 | 不做完整日志平台 | 第一轮先能定位服务为什么没起来 |

判断是否越界：如果某个主题不能帮助 P03 做到“拉代码后一键启动并能排查问题”，就先不要在 M07 深挖。

## 本模块工程练习主线

M07 的练习主线是：

```text
单服务容器化
-> 配置环境变量
-> 加入数据库和 Redis
-> 加入 worker
-> 用 compose 一键启动
-> 查看日志和排错
```

对应 P03 的目标是：

```text
FastAPI API
PostgreSQL / SQLite
Redis Streams
dispatcher + RAG Worker
可选：向量库或本地 mock RAG
```

第一轮不要追求生产级部署。只要能在本机稳定复现 P03 的最小服务组，就已经达到 M07 的核心目标。
RQ/Celery 只作为异步框架对比材料，不是当前 P03 Compose 的队列实现。

## 第 1 章：为什么需要容器化

### 1.1 本章目标

学完本章，你要理解 Docker 在当前路线中的位置：它不是为了炫技部署，而是为了让项目可复现、可交付、可排查。

### 1.2 没有 Docker 的问题

如果 P03 只靠本机环境运行，常见问题是：

```text
我的 Python 版本和你的不一样
我本地有 Redis，你没有
我的数据库端口被占用
worker 启动命令忘了
.env 配置没对齐
```

这些问题会让项目展示和复现实验很痛苦。

Docker 的价值是把运行环境也写成项目的一部分：

```text
代码 + 依赖 + 启动命令 + 服务依赖 + 配置约定
```

### 1.3 M07 和 P03 的关系

P03 至少包含多个服务：

| 服务 | 来源模块 | 容器化意义 |
|---|---|---|
| api | M02 | 对外提供 HTTP 接口 |
| rag_worker | M03/M06 | 后台执行 RAG 或模拟任务 |
| db | M06 | 保存任务、结果、状态 |
| redis | M06 | 队列和缓存 |
| metrics / load test | M08 | 后续压测和监控 |

M07 要做的事，是让这些服务能用一条命令启动：

```bash
docker compose up --build
```

### 1.4 常见错误

第一个错误：以为 Docker 只是部署工具。

在学习阶段，Docker 更重要的价值是复现环境。它让你知道项目依赖哪些服务、怎么启动、端口怎么暴露。

第二个错误：只容器化 API，不管数据库和 Redis。

P03 是多服务系统。只把 FastAPI 放进容器，还不能解决任务持久化和异步 worker 的复现问题。

第三个错误：把环境变量写死进代码。

数据库地址、Redis 地址、API key 都应该通过环境变量传入，而不是硬编码。

### 1.5 小练习

画出 P03 第一版需要容器化的服务：

```text
api
db
redis
worker
```

并说明每个服务从哪个模块来、启动失败会影响什么。

### 1.6 本章检查标准

- [ ] 能解释 Docker 为什么服务 P03 的复现和交付。
- [ ] 能列出 P03 第一版需要的服务。
- [ ] 能说明 M07 和 M02/M03/M06 的关系。

## 第 2 章：image 和 container

### 2.1 本章目标

本章只理解两个基础概念：image 和 container。

### 2.2 image 是什么

image 可以理解成“可运行环境的模板”。

它包含：

```text
基础系统
Python 运行环境
项目依赖
项目代码
默认启动命令
```

例如 `p03-api:dev` 这个镜像可以表示 P03 API 服务的运行模板。

### 2.3 container 是什么

container 是 image 的一个运行实例。

同一个 image 可以启动多个 container：

```text
p03-api image
-> api container
-> api-test container
```

第一轮只要记住：

```text
image 负责“怎么构建”
container 负责“怎么运行”
```

> **可迁移的原则**：镜像是可复现环境的版本化模板，容器是一次运行出来的进程边界。不要把临时容器里的手工修改当成项目成果；真正可交付的是 Dockerfile、依赖文件、启动命令和 compose 配置。

### 2.4 在 P03 中怎么用

P03 的 API 和 worker 可以用同一个镜像，但启动命令不同。

例如：

```text
api: uvicorn app.main:app --host 0.0.0.0 --port 8000
worker: python -m app.worker
```

这很常见：代码和依赖相同，但角色不同。

### 2.5 常见错误

第一个错误：每次改代码都以为要手动进容器改文件。

第一轮可以用 volume 挂载代码，或者重新 build 镜像。不要在容器里手改代码当正式流程。

第二个错误：分不清镜像和容器。

删除容器不等于删除镜像，重建镜像也不等于旧容器自动更新。

第三个错误：容器退出就以为 Docker 坏了。

容器通常是主进程结束后退出。要看日志判断为什么退出。

#### 踩坑现场：进容器手改代码，下一次启动全没了

很多初学者会 `docker exec` 进容器里改 Python 文件，发现服务暂时好了，就以为问题解决了。但容器是可替换实例，重新 build 或重建容器后这些修改会消失。正确做法是改宿主机项目文件，然后通过 bind mount 或重新 build 让修改进入容器。

### 2.6 小练习

用自己的话解释：

```text
为什么 API 和 worker 可以来自同一个 image？
为什么 container 退出后要先看 logs？
```

### 2.7 本章检查标准

- [ ] 能区分 image 和 container。
- [ ] 能解释为什么同一个镜像可以启动 API 和 worker。
- [ ] 能用日志判断容器退出原因。

## 第 3 章：最小项目结构

### 3.1 本章目标

在写 Dockerfile 之前，先把项目结构想清楚。容器化不是单独写一个文件，而是让项目具备清楚的启动边界。

### 3.2 P03 第一版结构

一个适合 M07 第一轮的最小结构可以是：

```text
p03-ai-workload-platform/
├─ app/
│  ├─ main.py
│  ├─ worker.py
│  ├─ settings.py
│  ├─ api/
│  ├─ services/
│  └─ repositories/
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
├─ .env.example
└─ README.md
```

每个文件的作用：

| 文件 | 作用 |
|---|---|
| `app/main.py` | FastAPI 入口 |
| `app/worker.py` | 后台 worker 入口 |
| `app/settings.py` | 读取环境变量 |
| `requirements.txt` | Python 依赖 |
| `Dockerfile` | 构建 API/worker 镜像 |
| `docker-compose.yml` | 启动多服务 |
| `.env.example` | 给出配置模板 |

### 3.3 为什么需要 .env.example

`.env` 通常不提交真实敏感配置。

但是项目必须提供 `.env.example`，告诉别人需要哪些配置：

```env
APP_ENV=dev
DATABASE_URL=postgresql://postgres:postgres@db:5432/p03
REDIS_URL=redis://redis:6379/0
API_PORT=8000
```

注意：在 compose 网络里，数据库主机名不是 `localhost`，而是服务名 `db`；Redis 主机名是 `redis`。

### 3.4 常见错误

第一个错误：没有固定启动入口。

如果 README 里写一堆手动步骤，Dockerfile 和 compose 就很难稳定。

第二个错误：`.env.example` 缺失。

别人不知道要配什么变量，项目就不可复现。

第三个错误：容器里还用 `localhost` 连数据库。

容器内部的 `localhost` 是它自己，不是其他服务。compose 中服务之间用服务名通信。

### 3.5 小练习

为 P03 写一个最小 `.env.example`，至少包含：

```text
DATABASE_URL
REDIS_URL
API_PORT
```

并说明为什么 compose 里要用 `db` 和 `redis` 作为主机名。

### 3.6 本章检查标准

- [ ] 能画出 P03 最小容器化项目结构。
- [ ] 能解释 `.env.example` 的作用。
- [ ] 能说明 compose 网络中服务名的意义。

## 第 4 章：最小 Dockerfile

### 4.1 本章目标

本章写一个能跑 FastAPI 的最小 Dockerfile，并理解每一行做什么。

### 4.2 最小 Dockerfile

```dockerfile
FROM python:3.13.2-slim-bookworm@sha256:6b3223eb4d93718828223966ad316909c39813dee3ee9395204940500792b740

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

解释：

| 行 | 含义 |
|---|---|
| `FROM python:3.13.2-slim-bookworm@sha256:...` | 对齐 Python 3.13 基线，并固定本次已验证镜像内容 |
| `ENV ...` | 不写 `.pyc`，并让容器日志立即刷新到标准输出 |
| `RUN useradd ...` | 创建固定 UID 的非 root 运行用户 |
| `WORKDIR /app` | 设置容器内工作目录 |
| `COPY requirements.txt .` | 先复制依赖文件 |
| `RUN pip install ...` | 安装依赖 |
| `COPY app ./app` | 复制项目代码；应用用户只需读取当前代码 |
| `USER appuser` | 后续进程不再以 root 身份运行 |
| `EXPOSE 8000` | 记录预期监听端口，但不会自动发布端口 |
| `CMD ...` | 默认启动 FastAPI |

`3.13.2` 和 digest 是本库 reference 在 2026-07-11 的已验证基线，不是永远不变的
“最新版”。更新基础镜像时要同时重建、运行测试并记录新 digest；第一次复现应先使用
仓库给出的基线，避免镜像内容在不知情时漂移。镜像标签和构建建议分别见
[Docker Hub Python Official Image](https://hub.docker.com/_/python) 与
[Docker build best practices](https://docs.docker.com/build/building/best-practices/)。

### 4.3 为什么先 COPY requirements

Docker 构建有缓存。

依赖文件不变时，`pip install` 这一层可以复用。代码变了，只需要重新复制代码层。

这是第一轮最值得掌握的构建优化。

> **可迁移的原则**：Dockerfile 的每一行都会形成构建层。把“变化慢”的依赖放前面，把“变化快”的业务代码放后面，是用构建缓存换开发效率；这不是镜像瘦身技巧，而是工程迭代速度问题。

### 4.4 API 和 worker 共用镜像

Dockerfile 的默认 `CMD` 可以启动 API。

worker 可以在 compose 里覆盖命令：

```yaml
command: python -m app.worker
```

这样 API 和 worker 共享同一份代码与依赖，不需要写两个 Dockerfile。

### 4.5 常见错误

第一个错误：忘记 `--host 0.0.0.0`。

FastAPI 如果只监听 `127.0.0.1`，容器外可能访问不到。

第二个错误：构建上下文太大。

如果没有 `.dockerignore`，可能把 `.venv`、缓存、数据文件都打进镜像。

第三个错误：在 Dockerfile 里写死环境配置。

配置应该通过 compose 的 `environment` 或 `.env` 注入。

第四个错误：应用一直以 root 身份运行。

即使第一轮只在本机实验，也应能用容器内 `id` 证明应用使用固定的非 root UID。非 root
不能替代网络、Secret 和文件权限设计，但能减少容器进程被利用后的默认权限。

### 4.6 最小 .dockerignore

```text
.venv
__pycache__
.pytest_cache
.git
*.pyc
data/
logs/
```

第一轮不追求极限镜像大小，但要避免把明显不该进镜像的东西复制进去。

### 4.7 小练习

写一个 P03 API 的 Dockerfile，并回答：

```text
为什么要 EXPOSE 8000？
为什么 uvicorn 要绑定 0.0.0.0？
为什么 requirements.txt 要先复制？
为什么要固定基础镜像 digest，并用非 root 用户运行？
```

构建后执行：

```powershell
docker build -t p03-api:learning .
docker run --rm p03-api:learning id
```

预期输出中的 `uid` 为 `10001`，且不能是 `0(root)`。这是 reference 镜像安全边界的
可观察证据；只有学习者亲手构建并记录输出，才计为 learner reproduction。

### 4.8 本章检查标准

- [ ] 能写最小 FastAPI Dockerfile。
- [ ] 能解释 Dockerfile 每一行。
- [ ] 能说明 API 和 worker 如何共用镜像。
- [ ] 能写最小 `.dockerignore`。
- [ ] 能证明镜像使用 Python 3.13 基线且进程 UID 不是 0。

## 第 5 章：volume 和数据持久化

### 5.1 本章目标

本章解决一个关键问题：容器删掉以后，数据是否还在？

### 5.2 为什么需要 volume

容器本身应该是可替换的。

如果数据库数据、上传文档、日志都只存在容器内部，容器删除后就没了。

所以需要 volume：

```text
container filesystem: 可以重建
volume: 保存需要持久化的数据
```

> **可迁移的原则**：容器应该是可丢弃的，业务事实不能是可丢弃的。P03 的 `tasks`、`result_json`、状态和错误记录属于事实，应通过数据库 volume 保留；Redis 缓存丢了可以变慢，但不应该丢任务。

### 5.3 P03 哪些数据需要保留

| 数据 | 是否需要 volume | 原因 |
|---|---|---|
| PostgreSQL 数据 | 需要 | tasks、结果、状态不能丢 |
| 上传文档 | 需要 | RAG 文档来源要保留 |
| 日志 | 可选 | 第一轮可以先看 docker logs |
| Redis 队列 | 第一轮可不持久化 | 长期事实以数据库为准 |
| 代码 | 开发时可 bind mount | 方便本地修改 |

### 5.4 compose 中的 volume

PostgreSQL 示例：

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: p03
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

这里的 `postgres_data` 是命名 volume。

### 5.5 常见错误

第一个错误：误删 volume。

`docker compose down` 通常不会删除 volume，但 `docker compose down -v` 会删除 volume。做实验前要知道这个区别。

#### 踩坑现场：以为 down 只是停服务，结果把实验数据删了

如果你在做 E06/E08 的实验记录，数据库里已经有任务状态、失败原因和延迟数据，执行 `docker compose down -v` 会把命名 volume 一起删掉。第一轮练习可以删，但必须先知道自己是在“清空实验环境”，而不是普通停止服务。

第二个错误：把代码和数据库数据混在同一个目录。

代码和数据生命周期不同，应该分开。

第三个错误：以为 Redis 缓存丢了就是系统丢数据。

第一轮设计里，Redis 是缓存和队列支撑，长期事实应在数据库。

### 5.6 小练习

解释下面两个命令的区别：

```bash
docker compose down
docker compose down -v
```

再说明 P03 里哪些数据不能随便删。

### 5.7 本章检查标准

- [ ] 能解释 volume 的作用。
- [ ] 能为 PostgreSQL 配置命名 volume。
- [ ] 能说明哪些数据需要持久化。
- [ ] 能解释 `down` 和 `down -v` 的区别。

## 第 6 章：network 和服务互通

### 6.1 本章目标

本章解决容器之间如何互相访问。

### 6.2 compose 默认网络

Docker Compose 会为项目创建默认网络。

同一个 compose 文件中的服务可以用服务名访问彼此：

```text
api -> db:5432
api -> redis:6379
worker -> db:5432
worker -> redis:6379
```

所以 `.env` 里写：

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/p03
REDIS_URL=redis://redis:6379/0
```

不要写：

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/p03
```

> **可迁移的原则**：容器网络里的 `localhost` 永远先指向“自己”。服务互通要使用 compose 服务名，比如 `db` 和 `redis`；宿主机访问容器才使用 `localhost:映射端口`。

### 6.3 端口映射是什么

端口映射用于让宿主机访问容器服务：

```yaml
ports:
  - "8000:8000"
```

意思是：

```text
宿主机 localhost:8000 -> api 容器 8000
```

数据库和 Redis 第一轮可以不暴露到宿主机，只给 compose 内部服务访问。开发调试时再按需暴露。

### 6.4 常见错误

第一个错误：容器里用 localhost 访问其他容器。

这是最常见错误之一。容器内 localhost 指向自己。

第二个错误：以为 `depends_on` 等于服务准备好了。

`depends_on` 只能控制启动顺序，不保证数据库已经可以接受连接。应用层要能重试连接，或者使用 healthcheck。

#### 踩坑现场：depends_on 写了，API 还是连不上数据库

`depends_on` 只表示 db 容器先启动，不表示 PostgreSQL 已经完成初始化并能接受连接。API 如果启动太快，仍然可能报 connection refused。第一轮最实用的做法是在应用连接数据库时加入短重试，或者给 db 增加 healthcheck 后再细化启动条件。

第三个错误：端口冲突。

如果宿主机 8000 已经被占用，compose 会启动失败，需要换成 `"8001:8000"`。

### 6.5 小练习

回答：

```text
api 容器如何访问 redis？
worker 容器如何访问 db？
宿主机浏览器如何访问 api？
```

### 6.6 本章检查标准

- [ ] 能解释 compose 服务名访问。
- [ ] 能区分容器内部端口和宿主机端口。
- [ ] 能排查 localhost 和端口冲突问题。

## 第 7 章：docker compose 串起 P03

<!-- textbook-content: type=design-note -->

### 7.1 本章目标

本章把 API、数据库、Redis、worker 串成一个最小 compose。

### 7.2 最小 compose

```yaml
services:
  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    ports:
      - "${API_PORT:-8000}:8000"
    env_file:
      - .env
    depends_on:
      - db
      - redis

  worker:
    build: .
    command: python -m app.worker
    env_file:
      - .env
    depends_on:
      - db
      - redis

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: p03
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7

volumes:
  postgres_data:
```

这个 compose 文件先解决最小启动，不追求生产级安全配置。

### 7.3 服务职责

| 服务 | 职责 |
|---|---|
| api | 接收请求，创建 task，返回 task_id |
| worker | 从队列或数据库读取任务，执行 RAG/模拟任务 |
| db | 保存 tasks、result_json、状态、错误 |
| redis | 支撑队列和缓存 |

### 7.4 和 M02/M03/M06 的连接

M02 给出 API：

```text
POST /tasks（task_type=rag_retrieval）
GET /tasks/{task_id}
GET /metrics
```

M03 给出 RAG worker 要执行的业务：

```text
query -> retrieve -> answer + retrieved_sources + metrics
```

M06 给出数据库和异步任务：

```text
tasks + outbox transaction -> dispatcher -> Redis Stream -> worker claim/CAS -> status update
```

M07 用 compose 把它们放到同一个可启动环境里。

> **可迁移的原则**：compose 文件不是“命令清单”，而是本地系统拓扑。它同时说明服务角色、启动命令、网络关系、持久化边界和配置来源，所以它天然承接 M02 API、M06 异步任务和 P03 项目交付。

### 7.5 常见错误

第一个错误：worker 没启动。

API 能创建任务，但任务一直 queued，常见原因就是 worker 容器没起来或报错退出。

#### 踩坑现场：API 正常返回 task_id，但任务一直 queued

这不是 RAG 一定坏了，也不一定是数据库坏了。先看 `docker compose ps` 里 worker 是否运行，再看 `docker compose logs worker`。如果 worker 没启动，M06 的状态流转就会停在 `queued`；如果 Redis 地址错，worker 可能根本拿不到任务。

第二个错误：API 连不上数据库。

检查 `DATABASE_URL` 是否使用 `db`，而不是 `localhost`。

第三个错误：Redis 地址写错。

检查 `REDIS_URL=redis://redis:6379/0`。

第四个错误：depends_on 后应用仍然启动失败。

数据库容器启动不等于数据库 ready，应用需要重试或等待。

### 7.6 小练习

写出 P03 compose 的四个服务，并为每个服务写一句：

```text
它依赖谁？
它失败后会导致什么现象？
用什么 logs 命令查看？
```

### 7.7 本章检查标准

- [ ] 能写出最小 `docker-compose.yml`。
- [ ] 能解释 api、worker、db、redis 的关系。
- [ ] 能用 compose 启动 P03 第一版服务组。
- [ ] 能判断任务一直 queued 是否和 worker 有关。

## 第 8 章：环境变量

### 8.1 本章目标

环境变量用于把配置从代码里拿出来。

### 8.2 P03 常见环境变量

```env
APP_ENV=dev
API_PORT=8000
DATABASE_URL=postgresql://postgres:postgres@db:5432/p03
REDIS_URL=redis://redis:6379/0
LOG_LEVEL=INFO
RAG_MODE=mock
```

如果后续接真实模型，还可能需要：

```env
OPENAI_API_KEY=...
```

真实 key 不应该提交进仓库。只提交 `.env.example`。

### 8.3 settings.py

Python 里可以集中读取配置：

```python
import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    rag_mode: str = "mock"


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ["REDIS_URL"],
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        rag_mode=os.environ.get("RAG_MODE", "mock"),
    )
```

### 8.4 常见错误

第一个错误：把 `.env` 提交到公开仓库。

第二个错误：本地和容器使用不同变量名。

第三个错误：配置缺失时报错不清楚。

第一轮可以先让缺失配置直接报错，但 README 或 `.env.example` 必须清楚。

### 8.5 小练习

写一份 `.env.example`，并说明哪些变量可以公开，哪些不能公开。

### 8.6 本章检查标准

- [ ] 能解释为什么配置不能写死。
- [ ] 能写 P03 最小 `.env.example`。
- [ ] 能通过 env_file 把配置注入 compose 服务。

## 第 9 章：日志和排查

### 9.1 本章目标

Docker 化后，排错方式会变。你要学会先看容器状态和日志。

### 9.2 常用命令

```bash
docker compose ps
docker compose logs api
docker compose logs worker
docker compose logs db
docker compose logs redis
docker compose logs -f api
```

### 9.3 常见故障表

| 现象 | 可能原因 | 先查什么 |
|---|---|---|
| API 容器退出 | 启动命令错、依赖缺失、配置缺失 | `docker compose logs api` |
| 访问 localhost:8000 失败 | 端口没映射、uvicorn 没绑定 0.0.0.0 | compose ports / api logs |
| API 连不上 db | DATABASE_URL 写 localhost、db 未 ready | env / db logs |
| 任务一直 queued | worker 没启动、Redis 地址错 | worker logs / redis logs |
| 数据重启后丢了 | 没配置 volume 或执行了 down -v | compose volumes |
| 修改代码不生效 | 没 rebuild 或 volume 挂载不对 | `docker compose up --build` |

### 9.4 日志和 M08 的关系

M07 阶段只要求能看日志排错。

M08 才会系统学习 Prometheus、Grafana、结构化指标和压测。

所以当前只需要做到：

```text
服务起不来 -> 看 logs
任务不执行 -> 看 worker logs
连接失败 -> 看 env 和 service name
```

> **可迁移的原则**：容器化之后，排错顺序要从“猜代码哪里错”变成“先确认服务是否存在、是否启动、是否连得上、是否拿到正确配置”。这条排查链以后进入 M08 监控时会升级成结构化日志和指标。

### 9.5 小练习

模拟三个错误并写排查记录：

- `DATABASE_URL` 写成 localhost。
- worker command 写错。
- API 端口映射冲突。

每个错误记录：

```text
现象
查看的命令
日志中的关键线索
修复方法
```

### 9.6 本章检查标准

- [ ] 能用 `docker compose ps` 查看服务状态。
- [ ] 能用 logs 定位 API、worker、db、redis 的问题。
- [ ] 能写出常见错误排查记录。

## 项目贯通案例：P03 一键启动

本案例把 M07 接回 P03。

目标：

```text
docker compose up --build
-> api 启动
-> db 启动并保留数据
-> redis 启动
-> worker 启动
-> POST /tasks 返回 task 与 created_new
-> GET /tasks/{task_id} 查询状态
```

### 最小启动检查

```bash
docker compose up --build
docker compose ps
docker compose logs api
docker compose logs worker
```

### 贯通验收

- [ ] API 能从宿主机访问。
- [ ] API 能连接 db。
- [ ] API 能连接 redis。
- [ ] worker 能启动并访问 db/redis。
- [ ] `POST /tasks` 能创建 `task_type=rag_retrieval` 任务，且安全字段只能来自服务端 principal。
- [ ] worker 能把任务从 queued/running 更新到 succeeded/failed。
- [ ] 数据库 volume 保留任务记录。
- [ ] 能用 logs 排查失败。

## 第 10 章：第一轮学习顺序

<!-- textbook-content: type=appendix -->

### 10.1 推荐顺序

1. 读第 1-2 章，理解 Docker 为什么服务复现和交付。
2. 读第 3 章，整理 P03 最小项目结构和 `.env.example`。
3. 读第 4 章，完成 E07-01：FastAPI 容器化。
4. 读第 5-7 章，完成 E07-02：compose 启动 API、DB、Redis、worker。
5. 读第 8 章，统一环境变量和配置读取。
6. 读第 9 章，练习 logs 排查。
7. 完成 E07-03：记录镜像大小、启动时间和常见错误。
8. 最后把 compose 启动说明写进 P03 README。

### 10.2 第一轮暂时不做

- 不做 Kubernetes。
- 不做 Service Mesh。
- 不做复杂 CI/CD。
- 不做生产级安全加固。
- 不做镜像极限瘦身。
- 不做多环境部署平台。
- 不做 Docker 底层源码。

### 10.3 本模块最终检查

- [ ] 能解释 image / container / Dockerfile / compose。
- [ ] 能写最小 FastAPI Dockerfile。
- [ ] 能写 api + db + redis + worker 的 compose。
- [ ] 能配置 volume、network、environment。
- [ ] 能用 logs 排查常见问题。
- [ ] 能说明 M07 如何承接 M02/M03/M06，并服务 P03 一键启动。

## 第 11 章：外部资料怎么用

<!-- textbook-content: type=reference -->

### 11.1 资料使用原则

资料按问题查，不从头泛读。

| 任务 | 优先资料 | 用法 |
|---|---|---|
| 理解 Docker 基础 | Docker Get Started | 看 image、container、Dockerfile 基本概念 |
| 写 Dockerfile | Dockerfile reference | 查 COPY、RUN、CMD、WORKDIR、EXPOSE |
| 写 compose | Docker Compose Docs | 查 services、ports、volumes、environment、depends_on |
| 做最小多服务示例 | Compose Getting Started | 对照最小 compose 思路 |

### 11.2 资料转化要求

每读一条资料，至少转化成下面之一：

- Dockerfile 行解释。
- compose 服务配置。
- `.env.example` 字段。
- E07 实验步骤。
- P03 README 启动说明。
- 常见错误排查记录。

如果不能转化，就先不要读。

## 暂时不要深入

- Kubernetes、Helm、Operator。
- Service Mesh、Ingress、复杂网关。
- GitHub Actions、复杂 CI/CD 发布流水线。
- 生产级镜像签名、SBOM、安全扫描。
- Docker 底层 namespace/cgroup 实现。
- 多节点部署、服务发现和负载均衡。

第一轮目标不是“懂所有容器技术”，而是：

```text
能把 P03 的 API、数据库、Redis、worker 和 RAG 服务稳定地 compose 启动、复现和排查。
```
