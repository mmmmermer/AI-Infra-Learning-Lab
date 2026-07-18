# E00-05 为任务排序函数写 pytest

## 实验定位

这个实验训练你用 pytest 验证一个最小任务排序函数。

M00 的重点不是学完 pytest，而是建立一个习惯：只要写了规则，就要用测试固定它。后续 P01 的 FIFO、Priority、SJF 调度策略都需要这种能力。

## 前置阅读

建议先读：

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]] 第 6 章：pytest 和最小质量保障
- [[20_资料库/模块资料索引/M00_工具链与计算机基础_资料索引]] 中 pytest 对应部分
- [[40_实验练习/E00_工具链基础实验/E00-04 写一个带日志的小脚本]]

## 实验目标

给任务排序函数写 3 个最小测试：

- 按创建时间排序
- 按优先级排序
- 按任务耗时排序

并故意制造一次失败，观察 pytest 输出。

## 推荐项目结构

```text
task_sorter/
├─ task_sorter.py
└─ tests/
   └─ test_task_sorter.py
```

## 第 1 步：准备业务代码

> 环境要求：使用 `py -3.13` 创建并激活项目 `.venv`。若 `python --version` 显示 3.8.6，先修复解释器选择，再运行 pytest。

`task_sorter.py`：

```python
def sort_by_created_at(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda task: task["created_at"])


def sort_by_priority(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda task: task["priority"])


def sort_by_duration(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda task: task["duration"])
```

## 第 2 步：准备测试目录

```powershell
mkdir tests
```

创建：

```text
tests/test_task_sorter.py
```

pytest 会自动发现 `test_*.py` 文件和 `test_` 开头的函数。

## 第 3 步：写第一个测试

```python
from task_sorter import sort_by_created_at


def test_sort_by_created_at():
    tasks = [
        {"id": "task-002", "created_at": 2, "priority": 1, "duration": 5},
        {"id": "task-001", "created_at": 1, "priority": 3, "duration": 1},
    ]

    result = sort_by_created_at(tasks)

    assert [task["id"] for task in result] == ["task-001", "task-002"]
```

运行：

```powershell
python -m pytest
```

## 第 4 步：补另外两个测试

```python
from task_sorter import sort_by_duration, sort_by_priority


def test_sort_by_priority():
    tasks = [
        {"id": "task-001", "created_at": 1, "priority": 3, "duration": 1},
        {"id": "task-002", "created_at": 2, "priority": 1, "duration": 5},
    ]

    result = sort_by_priority(tasks)

    assert [task["id"] for task in result] == ["task-002", "task-001"]


def test_sort_by_duration():
    tasks = [
        {"id": "task-001", "created_at": 1, "priority": 3, "duration": 10},
        {"id": "task-002", "created_at": 2, "priority": 1, "duration": 2},
    ]

    result = sort_by_duration(tasks)

    assert [task["id"] for task in result] == ["task-002", "task-001"]
```

## 第 5 步：故意制造失败

把 `sort_by_priority` 改错：

```python
def sort_by_priority(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda task: task["priority"], reverse=True)
```

再次运行：

```powershell
python -m pytest
```

观察 pytest 告诉你：

- 哪个测试失败
- 左边实际结果是什么
- 右边期望结果是什么
- 哪一行 assert 失败

## 第 6 步：修复并再次运行

把代码改回正确版本，然后再次运行测试。

```powershell
python -m pytest
```

预期：所有测试通过。

## 验收标准

- [ ] 能独立运行 `python -m pytest`
- [ ] 至少 3 个测试通过
- [ ] 能看懂失败信息
- [ ] 能解释每个测试保护了哪条规则
- [ ] 能故意制造失败并修复

## 常见错误

### 错误 1：测试文件命名不对

pytest 默认发现 `test_*.py` 或 `*_test.py`。建议统一使用：

```text
tests/test_task_sorter.py
```

### 错误 2：在错误目录运行 pytest

如果 pytest 找不到模块，先检查：

```powershell
pwd
ls
```

确认你在项目根目录。

### 错误 3：测试只看 print 输出

不要靠肉眼看输出。测试应该用 `assert` 明确判断结果。

## 和 P01 的关系

P01 的调度策略会越来越复杂。pytest 可以保护规则不被后续修改破坏。比如你以后优化 Priority 策略时，测试能提醒你有没有把优先级方向写反。

## 记录

### 测试用例


### 失败信息


### 修复过程


### 结论


## 关联

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_学习地图]]
- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]]
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_学习地图]]
- [[50_项目产出/P01_Mini_Scheduler/08_阶段执行说明_v0.1]]
