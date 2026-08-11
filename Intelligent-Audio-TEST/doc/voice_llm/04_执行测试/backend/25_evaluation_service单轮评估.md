# 25 — evaluation_service 单轮评估

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/utils/evaluation_service.py`

---

## 背景

多轮对话（用例配置了 `rounds`）中，每轮可以配置独立的评估（`round_evaluation_config`）。现有 `evaluate_case()` 对整个 `TestResult` 进行一次评估，不支持单轮粒度。

改造目标：`evaluate_case()` 支持接收 `round_number` 参数，对指定轮次的输出进行评估。触发条件为 `round_config.evaluationEnabled`，不绑定算法类型。

---

## 改造内容

### 1. `evaluate_case()` 新增 `round_number` 参数

```python
def evaluate_case(
    self,
    task_id: str,
    result_id: int,
    test_case_id: int,
    algorithm_result: Any,
    representative_dim_data: list[dict],
    group_items: list[tuple],
    algorithm_type: str,
    test_type: str,
    round_number: Optional[int] = None,  # 新增
):
    """
    对测试结果进行评估。

    Args:
        round_number: 轮次编号。None=整体评估, 0-based=单轮评估
    """
```

### 2. 单轮评估数据提取

当 `round_number` 不为 None 时，从 `algorithm_result` 中提取指定轮次的数据：

```python
def _extract_round_eval_data(self, algorithm_result, round_number):
    """从多轮结果中提取单轮评估数据"""
    if isinstance(algorithm_result, str):
        algorithm_result = json.loads(algorithm_result)

    rounds = algorithm_result.get('rounds', [])
    if round_number >= len(rounds):
        return None

    round_data = rounds[round_number]

    return {
        'output_text': round_data.get('output', {}).get('asr_text', ''),
        'input_text': round_data.get('input', {}).get('text', ''),
        'latency': round_data.get('latency'),
        'interruption': round_data.get('interruption'),
    }
```

### 3. evaluate_case 内部适配

```python
def evaluate_case(self, ..., round_number=None):
    # ... 现有逻辑 ...

    # 提取评估数据
    if round_number is not None:
        eval_data = self._extract_round_eval_data(algorithm_result, round_number)
        if eval_data is None:
            self._log('warning', f'轮次 {round_number} 数据不存在', task_id=task_id)
            return
        # 用单轮数据替换整体数据
        effective_algorithm_result = eval_data
    else:
        effective_algorithm_result = algorithm_result

    # ... 后续评估逻辑使用 effective_algorithm_result ...
```

### 4. TestResultDimension 记录关联

单轮评估创建的 `TestResultDimension` 记录需要标记轮次：

```python
# 创建 TestResultDimension 时
dim_record = TestResultDimension(
    test_result_id=result_id,
    dimension_id=dim_data['id'],
    dimension_name=dim_data['name'],
    status='pending',
    round_number=round_number,  # 新增字段
)
```

需要在 `TestResultDimension` 模型中新增 `round_number` 字段（Integer, nullable）。

### 5. 单轮评估 vs 整体评估调用方式

```python
# 整体评估（未配置 rounds 或用例最终聚合）
evaluation_service.evaluate_case(
    task_id, result_id, test_case_id,
    algorithm_result, dim_data, group_items,
    algorithm_type, test_type,
    round_number=None,
)

# 单轮评估（多轮用例中每轮，round_config.evaluationEnabled 为 true）
evaluation_service.evaluate_case(
    task_id, result_id, test_case_id,
    algorithm_result, dim_data, group_items,
    algorithm_type, test_type,
    round_number=0,  # 第 1 轮
)
```

### 6. 单轮评估在 E2E 循环中的调用

```python
# execute_e2e_case → 多轮循环内（case_config.rounds 非空时）
for round_idx, round_config in enumerate(rounds):
    # ... 播放、收集 ...

    # 检查是否配置了单轮评估
    if round_config.get('evaluationEnabled', False):
        round_eval_dims = round_config.get('evaluationDimensions', [])
        if round_eval_dims:
            self._evaluate_result(
                task_id=task_id,
                result_id=result_id,
                test_case_id=test_case_id,
                round_number=round_idx,
            )
```

---

## 不变部分

- 未配置多轮评估的用例仍使用 `round_number=None` 的整体评估
- 维度的 CRUD 和分组逻辑不变
- EndpointWorker 的请求处理逻辑不变

---

## 补充：结果解析配置化

`parse_dimension_result` 已改为配置驱动，不再依赖 `keywords` 字段兜底。

### 结果提取优先级

1. `EvaluationDimensionParam` 表中 `output_role=main` 的 `field_path`
2. output 参数中第一个有 `field_path` 的字段（兜底）
3. `api_settings.response_mapping`
4. 维度名匹配（兜底）

### output_params 加载

```python
# evaluation_service.py 加载维度数据时
for p in output_params:
    output_param_map.setdefault(p.dimension_id, []).append({
        'param_code': p.param_code,
        'field_path': p.field_path,
        'field_type': p.field_type,
        'agg_role': p.agg_role,
        'output_role': p.output_role,          # main / aux
        'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True
    })
```

### 辅助字段（output_role=aux）

辅助字段（如 errors/length）不需要创建子维度，只需配在主维度的 output 参数上：
- `output_role=aux`：不作为 `dimension_value` 的提取源
- `visible_in_report=false`：报告不显示该字段对应的维度列
- `agg_role=numerator/denominator`：聚合时从 `api_raw_response` 中按此角色提取

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `28_base_executor评估入队适配` | `_evaluate_result(round_number=...)` |
| `27_evaluation_result_processor多轮聚合` | 多轮评估结果处理 |
| `14_RoundEvaluationEditor` (frontend) | 前端轮次评估配置 |
