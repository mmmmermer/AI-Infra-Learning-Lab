# E02 后端 API 实验索引

## 当前状态

`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 not-evaluated`

E02-01 到 E02-03 共享同一个项目：`e02_service/`。不得为每一页重新创建 `FastAPI()`、独立 `TASKS` 或静态 metrics。

2026-07-13 验证环境：Python 3.13。reference 还必须通过服务端 principal、scope、跨 owner 404、
owner-scoped metrics、身份字段 422 和 OpenAPI bearer schema 契约；准确测试数以当次 pytest 输出为准。

## 累计路径

```text
E02-01 POST /tasks
-> E02-02 GET /tasks/{task_id}
-> E02-03 GET /metrics
```

三条运行路径都使用由 fixture bearer 凭据在服务端解析出的 `Principal(tenant_id, user_id, scopes)`。
请求体出现 `tenant_id/user_id/owner_id/permission_group` 等身份或授权字段必须返回 422；这不是完整
OAuth/JWT 实现，固定凭据也不得复制到生产环境。

| 实验 | 增量 | 验收 |
|---|---|---|
| [[E02-01 创建任务 API]] | TaskCreate、TaskRecord、server-owned principal、共享 repository | 认证 owner 创建后 repository 中真实存在任务；身份字段不能覆盖 principal |
| [[E02-02 查询任务状态 API]] | owner/tenant scoped 查询 | 能查到本人上一请求创建的 task；未知或跨 owner id 均返回 404 |
| [[E02-03 metrics API]] | 按 owner 从 repository 动态聚合 | 本人创建后计数变化；其他 owner 不可观察该计数 |

## 运行

```powershell
cd e02_service
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python -m uvicorn app.main:app --reload
```

参考实现已经验证，但学习者仍需亲手重建或修改并保留自己的测试记录，才能计入本人完成。
