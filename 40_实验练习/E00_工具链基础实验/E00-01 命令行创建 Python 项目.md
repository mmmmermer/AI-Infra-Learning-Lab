# E00-01 命令行创建 Python 项目

## 实验定位

这是 M00 的第一个实验。它不追求写复杂代码，只训练一件事：你能不能独立在命令行里创建一个 Python 项目，并确认自己到底在哪个目录、运行的是哪个文件。

如果这一步不熟，后面的 pytest、Git、FastAPI、Docker 都会变成“我不知道命令在哪里执行”的混乱状态。

## 前置阅读

建议先读：

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]] 第 2 章：Shell、目录和路径
- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]] 第 3 章：Python 解释器、pip 和虚拟环境

## 实验目标

完成一个最小项目 `task_sorter`：

- 能创建目录
- 能进入目录
- 能创建 `main.py`
- 能运行 `python main.py`
- 能确认当前 Python 解释器
- 能解释当前工作目录是什么

## 推荐项目位置

可以放在你的练习目录或项目目录中，例如：

```text
.\code-labs\task_sorter
```

如果你还没有 `code-labs` 目录，可以先创建。

## 第 1 步：确认当前位置

在 PowerShell 中执行：

```powershell
pwd
```

它会显示当前工作目录。

你需要理解：终端执行命令时，默认以当前工作目录为起点。

## 第 2 步：创建项目目录

```powershell
mkdir task_sorter
cd task_sorter
```

再次确认位置：

```powershell
pwd
```

预期：路径最后应该是 `task_sorter`。

## 第 3 步：创建 `main.py`

如果用 VS Code / Cursor，可以在编辑器里新建文件。

文件内容：

```python
print("task_sorter is running")
```

目录结构应该是：

```text
task_sorter/
└─ main.py
```

## 第 4 步：运行 Python 文件

```powershell
python main.py
```

预期输出：

```text
task_sorter is running
```

如果没有输出，先检查：

- 文件是不是叫 `main.py`
- 终端是不是在 `task_sorter` 目录下
- 文件里是不是保存了代码

## 第 5 步：确认当前 Python

```powershell
python -c "import sys; print(sys.executable)"
```

这个命令会输出当前使用的 Python 程序路径。

你现在不需要记住所有路径细节，只要知道：以后出现“我明明安装了包但 Python 找不到”的问题时，第一步就是检查当前 Python 是哪一个。

## 第 6 步：创建虚拟环境

```powershell
python -m venv .venv
```

激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

激活后再次确认 Python：

```powershell
python -c "import sys; print(sys.executable)"
```

预期：路径中应该包含 `.venv`。

## 第 7 步：安装 pytest

```powershell
python -m pip install pytest
```

确认安装：

```powershell
python -m pytest --version
```

## 验收标准

- [ ] 能说出当前终端在哪个目录
- [ ] 能解释 `main.py` 文件在哪里
- [ ] 能运行 `python main.py`
- [ ] 能创建并激活 `.venv`
- [ ] 能解释为什么优先用 `python -m pip`
- [ ] 能确认当前 Python 路径

## 常见错误

### 错误 1：终端不在项目目录

现象：

```text
python: can't open file 'main.py'
```

排查：

```powershell
pwd
ls
```

如果 `ls` 看不到 `main.py`，说明你不在文件所在目录。

### 错误 2：PowerShell 不允许激活虚拟环境

可能出现：

```text
running scripts is disabled on this system
```

先记录这个问题，不要硬改系统策略。可以临时用：

```powershell
.venv\Scripts\python.exe main.py
```

后续再专门处理执行策略。

### 错误 3：安装包后还是找不到

优先检查：

```powershell
python -c "import sys; print(sys.executable)"
python -m pip list
```

不要只看 `pip list`，要看 `python -m pip list`。

## 和 P01 的关系

P01 Mini Scheduler 最开始也是一个 Python 小项目。这个实验就是 P01 的地基：后面所有调度策略、测试、日志、README，都会在这个项目结构里继续长出来。

## 记录

### 当前项目路径


### 当前 Python 路径


### 成功输出


### 遇到的问题


### 解决过程


### 结论


## 关联

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_学习地图]]
- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]]
- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页]]
