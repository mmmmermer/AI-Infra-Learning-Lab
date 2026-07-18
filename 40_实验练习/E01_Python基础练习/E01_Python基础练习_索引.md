# E01 Python 基础练习索引

## 定位

用于把 Python 语法、函数、类、模块、测试和小脚本能力练到能支持 P01 Mini Scheduler。

这一组练习不是泛泛学 Python，而是直接服务 P01 v0.1：从任务排序脚本走向可测试的小型调度器。

## 推荐实验

- [[40_实验练习/E01_Python基础练习/E01-01 任务排序脚本|E01-01 任务排序脚本]]：先用 dict/list 实现 FIFO、Priority、SJF 排序
- [[40_实验练习/E01_Python基础练习/E01-02 Python 类实现 Task 和 Worker|E01-02 Python 类实现 Task 和 Worker]]：用 dataclass 建模任务和 worker
- [[40_实验练习/E01_Python基础练习/E01-03 pytest 测试调度器|E01-03 pytest 测试调度器]]：用 pytest 固定调度规则
- [[40_实验练习/E01_Python基础练习/E01-04 并发选择与取消|E01-04 并发选择与取消]]：区分 thread/process/asyncio，并验证阻塞、取消、超时和资源释放

## 建议顺序

1. 先完成 E01-01，确认排序规则能跑通
2. 再完成 E01-02，把数据从 dict 升级成 dataclass
3. 再完成 E01-03，给调度规则补测试
4. 完成 E01-04，为 M02 的 async 服务、deadline 和取消建立心智模型
5. 最后回到 P01 项目页，整理代码结构和实验记录

## 对应模块

- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材]]
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_学习地图]]
- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页]]
- [[50_项目产出/P01_Mini_Scheduler/08_阶段执行说明_v0.1]]

## 完成后应该沉淀

- 一份可运行的 `mini_scheduler` 代码骨架
- 至少 5 个 pytest
- E01-04 的 6 项标准库契约测试与一份并发选择说明
- 一条或多条问题记录
- 一篇 P01 项目实验记录

## 前置资料

- [[20_资料库/模块资料索引/M01_Python工程能力_资料索引|M01 Python 工程能力资料索引]]
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材|M01 Python 工程能力适配教材]]

实验前不需要把全部资料读完。建议按资料索引里的“当前只读哪些部分”边读边做，优先把每次阅读转成可运行代码和测试。
