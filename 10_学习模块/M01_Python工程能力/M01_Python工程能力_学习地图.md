# M01 Python 工程能力学习地图

## 怎么读这个模块

把 M01 当成“为了亲手写出 P01 Mini Scheduler”而学的 Python 工程课，不要当成语法大全。

每章都围绕一个问题读：这个知识点如何帮助我把 Task、Worker、调度策略、指标计算和测试拆清楚？如果一节内容暂时不能服务小项目，就先知道位置，不深挖。

读完一节后，最好立刻写 10 到 30 行小代码，而不是只做笔记。

## 在总路线中的位置

Python 是两个月快速上手阶段的主语言，用于后端服务、RAG/Agent、调度器、实验脚本和数据分析。

## 要解决的问题

- 能否不完全依赖 AI，独立读懂、修改、调试项目代码？
- 能否写出结构清晰、可测试、可维护的小型 Python 工程？
- 能否把实验脚本、服务代码和项目逻辑分开？

## 学习内容
- 基础语法复盘：变量、条件、循环、list、dict
- 函数：把排序、校验、指标计算拆成可测试单元
- 类和数据模型：用 `dataclass` 表达 `Task`、`Worker`
- 模块和包：把 `models.py`、`strategies.py`、`metrics.py`、`tests/` 分清楚
- 类型标注：让函数输入输出和数据对象更清楚
- 异常处理：对缺字段、非法值、文件不存在给出明确错误
- JSON 和文件读写：读取任务输入、保存实验结果
- logging：记录关键运行过程，用于调试和复盘
- pytest：验证排序策略、边界情况和错误输入
- argparse / 简单配置：只在需要命令行参数时查最小用法
- HTTPX：作为后续 API 请求的选读入口，不作为 M01 主线
- 项目目录结构：把脚本整理成 P01 Mini Scheduler 的最小工程

## 学习目标

- 能把一个小需求拆成数据模型、函数、模块和测试。
- 能用 `dataclass` 和类型标注表达核心对象。
- 能把排序、校验、IO 和测试分层放好。
- 能用 `pytest` 证明调度规则没有写错。
- 能按项目需要去查官方文档，而不是靠零散记忆。

## 对应资料
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材|M01 适配教材]]
- [[20_资料库/模块资料索引/M01_Python工程能力_资料索引|M01 资料索引]]
- [[20_资料库/官方文档/00_索引|官方文档索引]]
- [Python Tutorial](https://docs.python.org/3/tutorial/)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Python typing](https://docs.python.org/3/library/typing.html)
- [Python pathlib](https://docs.python.org/3/library/pathlib.html)
- [Python json](https://docs.python.org/3/library/json.html)
- [pytest 官方文档](https://docs.pytest.org/)
- [Pydantic 官方文档](https://docs.pydantic.dev/)
- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页|P01 项目主页]]

## 对应知识卡片
这些卡片后续会随着学习过程逐步沉淀，先按问题去建，不先假设它们已经存在。

- 异常处理
- Python 项目结构
- pytest fixture
- dataclass 和类型标注
- JSON 与文件读写
- 模块拆分
- logging 与调试

## 对应实验

- [[E01-01 任务排序脚本]]
- [[E01-02 Python 类实现 Task 和 Worker]]
- [[E01-03 pytest 测试调度器]]

## 对应项目

- [[P01_Mini_Scheduler 项目主页]]
- [[P03_AI_Workload_Platform 项目主页]]

## 检查标准
- [ ] 能独立写出 `Task`、`Worker`、FIFO、Priority、SJF 的最小实现
- [ ] 能把代码拆成 `models.py`、`strategies.py`、`metrics.py` 和 `tests/`
- [ ] 能写至少 5 个 pytest，覆盖正常排序、空输入、相同优先级和错误输入
- [ ] 能读取一个 JSON 任务文件，并把硬编码样例迁移到文件输入
- [ ] 能用 logging 记录输入数量、策略名称、输出顺序或异常信息
- [ ] 能读懂 AI 生成代码并指出边界混乱、函数过大、测试缺失等问题
- [ ] 能把一次实验结果写回 P01 项目记录

## 暂时不深入

- 不在 M01 深入异步 Python、元编程、描述符、复杂泛型和包发布。
- 不把爬虫、GUI、数据分析全家桶作为当前主线。
- 不提前学习大型框架源码；FastAPI、Celery、Ray、Kubernetes 放到后续模块和项目阶段。
- 不追求一次写出完美架构，先把 `Task`、`Worker`、排序策略、测试和指标做清楚。
