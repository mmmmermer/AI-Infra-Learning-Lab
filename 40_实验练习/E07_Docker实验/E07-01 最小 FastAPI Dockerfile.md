# E07-01 最小 FastAPI Dockerfile

> 状态（2026-07-18）：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 not-evaluated`。本页仍只验收 API 镜像本身；同一镜像已进一步进入 E07-02/E07-03 的 PostgreSQL、Redis、dispatcher 和独立 worker Compose 闭环。

## 实验目的

本实验把 P03 的 FastAPI API 服务打包成最小 Docker 镜像。

目标不是做生产级镜像优化，而是先验证：

```text
项目代码
-> Dockerfile
-> docker build
-> docker run
-> /health 可访问
-> 后续能进入 docker compose
```

完成后，你应该能解释 API 容器为什么必须绑定 `0.0.0.0`，为什么配置要从环境变量读取，以及为什么 API 和 worker 后续可以复用同一个镜像。

## 项目结构

当前已验证的参考结构：

```text
p03_service/
├─ app/
│  ├─ main.py
│  ├─ worker.py
│  └─ store.py
├─ tests/
├─ requirements-runtime.lock
├─ Dockerfile
├─ .dockerignore
└─ compose.yaml
```

本实验只验证单服务镜像边界。数据库、Redis、独立 worker 和持久化的证据必须分别引用 E07-02/E07-03，不能仅从 `/health` 外推。

## 配置文件

### app/main.py

```python
from fastapi import FastAPI

app = FastAPI(title="P03 AI Workload Platform")


@app.get("/health")
def health_check():
    return {"status": "ok"}
```

### requirements-runtime.lock

```text
fastapi==0.116.1
uvicorn==0.35.0
```

实际锁文件还包含 FastAPI 的传递依赖，以及 Compose 模式使用的 `psycopg`、`psycopg-binary` 和 `redis`。这里的片段只解释最小 API 镜像入口。

### Dockerfile

```dockerfile
FROM python:3.13.2-slim-bookworm@sha256:6b3223eb4d93718828223966ad316909c39813dee3ee9395204940500792b740

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-runtime.lock ./
RUN python -m pip install --requirement requirements-runtime.lock \
    && useradd --create-home --uid 10001 appuser

COPY app ./app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### .dockerignore

```text
.venv
__pycache__
.pytest_cache
*.pyc
```

当前参考实现没有读取 `.env`。以后引入配置文件时，`.env` 必须加入 `.dockerignore`，真实配置由 compose 的 `env_file` 或 `environment` 注入。

## 启动命令

```powershell
cd 50_项目产出\P03_AI_Workload_Platform\p03_service
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/health
docker compose logs --no-color api
docker compose down
```

期望返回：

```json
{"status":"ok"}
```

`compose.yaml` 把宿主机 `8001` 映射到容器 `8000`，避免和本地开发服务常用的 `8000` 冲突。

## 环境变量

在 E07-01 的 `memory` 模式下 API 不连接数据库和 Redis；Compose 的 `postgres` 模式已经在 E07-02/E07-03 验证。下面变量用于理解两种模式的配置边界。

`.env.example` 可以先写：

```text
APP_ENV=dev
API_PORT=8000
LOG_LEVEL=INFO
DATABASE_URL=postgresql://postgres:postgres@db:5432/p03
REDIS_URL=redis://redis:6379/0
RAG_MODE=mock
```

注意：容器内连接 db/redis 时不能写 `localhost`。在 compose 网络里，应使用服务名 `db` 和 `redis`。

## volume

E07-01 暂时不需要 volume。

如果为了本地开发把代码挂进容器，可以后续在 compose 中写：

```yaml
volumes:
  - ./app:/app/app
```

第一轮记录这个概念即可，不要求热更新。

## network

单容器 `docker run` 时只需要端口映射：

```text
host localhost:8000 -> container 8000
```

E07-02/E07-03 中，API、db、redis、dispatcher、worker 已进入同一个 compose network，并通过服务名通信。

## 日志

查看 API 容器日志：

```bash
docker ps
docker logs <container_id>
```

如果使用 compose：

```bash
docker compose logs api
```

日志里至少应看到 Uvicorn 启动信息和监听端口。

## 常见错误

| 现象 | 常见原因 | 排查方式 | 修复方向 |
|---|---|---|---|
| `curl localhost:8000` 失败 | uvicorn 绑定了 `127.0.0.1` | 看启动命令 | 改为 `--host 0.0.0.0` |
| build 很慢 | 依赖太多或缓存失效 | 看 Dockerfile COPY 顺序 | 先 COPY requirements，再安装依赖 |
| 容器启动后立即退出 | CMD 写错或依赖缺失 | `docker logs` | 修正 CMD 或 requirements |
| 配置泄露 | 把 `.env` COPY 进镜像 | 检查 `.dockerignore` | `.env` 加入 `.dockerignore` |

## 连接 P03

本实验只证明 API 镜像能启动。P03 的持久化接口在 E07-02/E07-03 中贯通：

```text
POST /tasks -> 创建 mock_rag / mock_agent / simulated_inference task
GET /tasks/{task_id} -> 查询任务状态
dispatcher/worker -> 发布、消费并回写状态
```

E07-01 是这条链路的容器化入口。

## 参考脱敏合规 AI 案例

脱敏合规 AI 案例项目的 compose 中使用了 postgres、redis、qdrant、minio 等服务，并给 postgres/redis 配了 volume 和 healthcheck。

本实验只参考它的结构意识：

- 服务拆分清楚。
- 数据服务有 volume。
- 基础服务有 healthcheck。

不要直接把 qdrant/minio 复制成 P03 第一轮必需服务。P03 第一轮先保证 API 镜像稳定构建和启动。

## 记录表

| image_name | build_time | image_size | container_status | exposed_port | health_result | log_excerpt | error_type | fix_notes |
|---|---:|---:|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |

## 参考验证证据

2026-07-10 已实际验证：

- 镜像 `p03-service:0.2.0` 构建成功，Python 基础镜像使用固定 digest。
- 容器状态为 `healthy`，运行用户为 `appuser`。
- `/health` 返回 `{"status":"ok"}`。
- HTTP 闭环完成 `POST /tasks -> POST /workers/run-next -> GET /tasks/{task_id} -> GET /metrics`。
- 任务最终为 `succeeded`，队列长度回到 `0`，清理后无遗留 compose 容器和网络。

## 学习者验收标准

- [ ] 能写出最小 FastAPI `Dockerfile`。
- [ ] 能构建 `p03-api:dev` 镜像。
- [ ] 能运行容器并访问 `/health`。
- [ ] 能解释 `EXPOSE` 和 `ports` 的区别。
- [ ] 能解释为什么 uvicorn 要绑定 `0.0.0.0`。
- [ ] 能说明 `.env` 为什么不能复制进镜像。
- [ ] 能复现完整 HTTP 任务闭环并保存自己的运行记录。

## 边界提醒

本实验不做多阶段构建极限优化、不做镜像安全扫描、不做生产级密钥管理，不做服务网格或复杂 CI/CD，也不进入 Kubernetes。
