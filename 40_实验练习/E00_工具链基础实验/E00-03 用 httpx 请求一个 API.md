# E00-03 用 httpx 请求一个 API

## 实验定位

这个实验训练你理解 HTTP 请求、响应、状态码和 JSON。

后续 FastAPI、RAG 服务、Agent 工具调用、向量数据库接口，本质上都会用到类似的请求-响应模型。现在先不写服务端，只从客户端发起一次请求，观察返回结果。

## 前置阅读

建议先读：

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]] 第 7 章：HTTP、JSON 和服务交互
- [[20_资料库/模块资料索引/M00_工具链与计算机基础_资料索引]] 中 MDN HTTP 和 HTTPX 对应部分

## 实验目标

完成一个 Python 脚本：

- 安装 `httpx`
- 请求一个公开测试 API
- 打印 HTTP 状态码
- 解析 JSON
- 处理最小异常

## 推荐代码位置

```text
task_sorter/
└─ examples/
   └─ request_demo.py
```

如果还没有 `examples` 目录，可以新建。

## 第 1 步：确认虚拟环境

```powershell
python -c "import sys; print(sys.executable)"
```

确认路径里包含 `.venv`。

如果还没有安装 `httpx`：

```powershell
python -m pip install httpx
```

## 第 2 步：写最小请求脚本

```python
import httpx

url = "https://httpbin.org/json"
response = httpx.get(url, timeout=10.0)

print("status_code=", response.status_code)
print("content_type=", response.headers.get("content-type"))

payload = response.json()
print("top_level_keys=", list(payload.keys()))
```

运行：

```powershell
python examples/request_demo.py
```

## 第 3 步：理解输出

你应该看到类似信息：

```text
status_code= 200
content_type= application/json
top_level_keys= ['slideshow']
```

重点理解：

- `status_code=200` 表示请求成功
- `headers` 是响应元信息
- `response.json()` 把 JSON 转成 Python dict/list

## 第 4 步：加入异常处理

网络请求可能失败，所以最小脚本应该处理异常。

```python
import httpx

url = "https://httpbin.org/json"

try:
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
except httpx.HTTPError as exc:
    print(f"request failed: {exc}")
else:
    payload = response.json()
    print("status_code=", response.status_code)
    print("top_level_keys=", list(payload.keys()))
```

## 第 5 步：记录失败信息

故意把地址改错，例如：

```python
url = "https://httpbin.org/status/500"
```

观察输出。

你要学会记录：

- 请求地址
- 状态码
- 错误信息
- 是否超时
- 返回内容是否是 JSON

## 验收标准

- [ ] 能安装 `httpx`
- [ ] 能发出 GET 请求
- [ ] 能解释 status code 200
- [ ] 能把 JSON 响应转成 Python 对象
- [ ] 能处理一次请求失败
- [ ] 能说明后续 FastAPI/RAG 为什么需要 HTTP/JSON

## 常见错误

### 错误 1：没有安装到当前虚拟环境

排查：

```powershell
python -c "import sys; print(sys.executable)"
python -m pip show httpx
```

### 错误 2：网络访问失败

不要马上怀疑代码。先记录：

- 是否能打开网页
- 是否超时
- 是否被代理或网络环境影响

### 错误 3：直接假设响应一定是 JSON

真实接口可能返回 HTML、错误文本或空内容。后续工程代码要检查状态码和 content type。

## 和 P01 / 后续模块的关系

P01 后续服务化会用 FastAPI 暴露任务接口，P02 RAG/Agent 服务会通过 HTTP 调用模型、检索服务或工具 API。这个实验先建立最小直觉：服务之间经常是通过 HTTP + JSON 交换数据。

## 记录

### 代码位置


### 请求 URL


### 输出结果


### 失败案例


### 结论


## 关联

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_学习地图]]
- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]]
- [[10_学习模块/M02_后端API与服务化/M02_后端API与服务化_学习地图]]
