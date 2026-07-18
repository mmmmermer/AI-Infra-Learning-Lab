# GF07-02 baseline vs ML 模型

> 环境前置：使用 `finance_reference/requirements-dev.lock` 中固定的 scikit-learn 1.9.0，
> 不执行无版本的 `pip install scikit-learn`。GF07-01 必须先通过三集合非空和 train 两类别断言。

## 实验定位

本实验承接 GF07-01，目标是建立一个 baseline，再用一个简单 challenger model 做同口径对比。

重点不是模型复杂度，而是：

```text
没有 baseline，就不知道模型有没有价值。
```

## 前置阅读

- [[40_实验练习/GF10_金融工程全阶段实验候选/GF07-01 金融分类任务的时间切分|GF07-01 金融分类任务的时间切分]]
- [[10_学习模块/F07_金融机器学习与模型风险/F07_金融机器学习与模型风险_适配教材|F07 金融机器学习与模型风险适配教材]]

## 实验目标

- [ ] 能建立 majority-class baseline。
- [ ] 能训练一个简单逻辑回归模型。
- [ ] 能在同一个 test set 上比较 baseline 和 model。
- [ ] 能记录 accuracy、precision、recall、F1 和 confusion matrix。
- [ ] 能保存失败样例。

## 输入数据

使用 GF07-01 生成的：

```text
train
validation
test
features
label
```

## 实验步骤

### 步骤 1：建立 baseline

```python
majority_class = train["label"].mode()[0]
test = test.copy()
test["baseline_pred"] = majority_class
```

### 步骤 2：训练简单模型

```python
from sklearn.linear_model import LogisticRegression

model = LogisticRegression(solver="liblinear", random_state=20260711)
model.fit(train[features], train["label"])
validation = validation.copy()
validation["model_pred"] = model.predict(validation[features])
```

先在 validation 记录候选表现和失败样例。模型、特征、阈值和评测口径冻结后，才允许读取
final test 一次：

```python
test = test.copy()
test["model_pred"] = model.predict(test[features])
```

### 步骤 3：计算指标

```python
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

def eval_pred(y_true, y_pred):
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }

validation_model_metrics = eval_pred(
    validation["label"], validation["model_pred"]
)
baseline_metrics = eval_pred(test["label"], test["baseline_pred"])
final_model_metrics = eval_pred(test["label"], test["model_pred"])
```

### 步骤 4：保存失败样例

```python
failure_examples = test[test["label"] != test["model_pred"]].head(5)
```

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF07-02 |
| base_experiment | GF07-01 |
| baseline_rule | majority_class |
| model_type | logistic_regression |
| feature_list |  |
| validation_metrics |  |
| test_date_range |  |
| baseline_metrics |  |
| model_metrics |  |
| test_access_count | 1（仅冻结后） |
| confusion_matrix |  |
| failure_examples |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 只报告模型，不报告 baseline。
- baseline 和 model 用了不同测试集。
- 只看 accuracy，不看 confusion matrix。
- 不保存失败样例。
- 把分类指标写成交易收益。

## 验收标准

- [ ] baseline 和 model 使用同一个 test set。
- [ ] 所有选择只使用 validation，final test 在方案冻结后读取一次。
- [ ] 已记录 baseline_metrics 和 model_metrics。
- [ ] 已记录 confusion_matrix。
- [ ] 已保存失败样例。
- [ ] 能说明模型指标不等于投资能力。

## 关联 P03 字段

```json
{
  "task_type": "evaluation_task",
  "result_json": {
    "baseline_metrics": "calculated",
    "model_metrics": "calculated",
    "confusion_matrix": "calculated",
    "failure_examples": "recorded",
    "limitations": ["small sample", "no investment advice"]
  }
}
```
