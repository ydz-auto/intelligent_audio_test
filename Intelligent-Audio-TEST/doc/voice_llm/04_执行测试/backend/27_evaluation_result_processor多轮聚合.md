# 27 — evaluation_result_processor 多轮聚合

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/services/evaluation/evaluation_result_processor.py`、`backend/utils/report/aggregation_strategies.py`、`backend/utils/report/report_utils.py`

---

## 背景

voice_llm 多轮对话中，每轮独立评估会产生多条 `TestResultDimension` 记录（每条带 `round_number`）。在所有轮次评估完成后，需要聚合计算全局评估分数，更新到 `algorithm_result` 的 `aggregated` 字段和 `TestResult` 的最终得分。

---

## 改造内容

### 1. 新增 `aggregate_round_results()` 方法

```python
def aggregate_round_results(
    self,
    result_id: int,
    task_id: str,
    test_case_id: int,
) -> dict:
    """
    聚合多轮评估结果，计算全局分数。

    Returns:
        {
            "avg_wer": 0.05,
            "avg_llm_judge": 4.2,
            "avg_latency": 1.83,
            "round_count": 3,
            "completed_rounds": 3
        }
    """
```

### 2. 核心逻辑

```python
def aggregate_round_results(self, result_id, task_id, test_case_id):
    from flask import current_app
    app = current_app._get_current_object()

    with app.app_context():
        # 查询该 result 下所有维度评估结果
        dim_results = db.session.query(TestResultDimension).filter(
            TestResultDimension.test_result_id == result_id
        ).all()

        # 按维度名称分组
        dim_groups = {}
        for dr in dim_results:
            key = dr.dimension_name
            if key not in dim_groups:
                dim_groups[key] = []
            dim_groups[key].append({
                'round_number': dr.round_number,
                'score': dr.score,
                'raw_value': dr.raw_value,
                'status': dr.status,
            })

        # 计算每个维度的加权平均
        aggregated = {}
        for dim_name, results in dim_groups.items():
            completed = [r for r in results if r['status'] == 'completed' and r['score'] is not None]
            if completed:
                avg_score = sum(r['score'] for r in completed) / len(completed)
                aggregated[f'avg_{dim_name}'] = round(avg_score, 4)
            else:
                aggregated[f'avg_{dim_name}'] = None

        aggregated['round_count'] = len(set(
            r['round_number'] for r in dim_results if r['round_number'] is not None
        ))
        aggregated['completed_rounds'] = len(set(
            r['round_number'] for r in dim_results
            if r['round_number'] is not None and r['status'] == 'completed'
        ))

        # 更新 algorithm_result 中的 aggregated 字段
        self._update_algorithm_result_aggregated(result_id, aggregated)

        return aggregated
```

### 3. 更新 algorithm_result

```python
def _update_algorithm_result_aggregated(self, result_id, aggregated):
    """将聚合结果写入 TestResult.algorithm_result"""
    test_result = db.session.query(TestResult).filter(
        TestResult.id == result_id
    ).first()

    if test_result and test_result.algorithm_result:
        result_data = test_result.algorithm_result
        if isinstance(result_data, str):
            result_data = json.loads(result_data)

        result_data['aggregated'] = aggregated
        test_result.algorithm_result = json.dumps(result_data, ensure_ascii=False)
        db.session.commit()
```

### 4. `update_task_case_status` 适配

```python
def update_task_case_status(self, result_id, current_result_all_completed,
                             task_id, test_case_id, test_type):
    # 现有逻辑...

    # 多轮场景：检查所有轮次的维度评估是否完成
    if self._is_multi_round_result(result_id):
        all_done = self._check_all_round_dimensions_completed(result_id)
        if all_done:
            # 聚合多轮结果
            aggregated = self.aggregate_round_results(result_id, task_id, test_case_id)
            # 标记为完成
            self._mark_result_completed(result_id, aggregated)
    else:
        # 现有单次评估逻辑
        ...
```

### 5. 多轮完成判断

```python
def _is_multi_round_result(self, result_id):
    """判断是否为多轮评估结果"""
    dim_results = db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id == result_id,
        TestResultDimension.round_number.isnot(None),
    ).first()
    return dim_results is not None

def _check_all_round_dimensions_completed(self, result_id):
    """检查多轮结果中所有维度评估是否完成"""
    pending_count = db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id == result_id,
        TestResultDimension.status == 'pending',
    ).count()
    return pending_count == 0
```

### 6. 聚合策略（配置驱动 + 策略模式）

聚合方式不再硬编码，改为通过 `Dimension.statistic_method` 字段配置，由 `AggregationStrategy` 策略类统一调度。

#### 策略注册

| statistic_method | 策略类 | 说明 |
|-----------------|--------|------|
| `average` | `SimpleAverageStrategy` | 简单算术平均（默认） |
| `weighted_wer` | `WeightedSumRatioStrategy` | 加权 WER = Σ分子 / Σ分母 |

#### 策略接口

```python
class AggregationStrategy(ABC):
    @abstractmethod
    def aggregate(self, items: List[Dict[str, Any]], output_params: List[Dict[str, Any]] = None) -> Optional[float]:
        pass
```

#### WeightedSumRatioStrategy 实现

```python
class WeightedSumRatioStrategy(AggregationStrategy):
    """
    加权比率：Σ(numerator) / Σ(denominator)。
    按 agg_role 找分子和分母的 field_path，从每条结果的 api_raw_response 提取值后累加。
    典型场景：WER = Σerrors / Σlength（按字数加权）。
    """
    def aggregate(self, items, output_params=None):
        numerator_path = _find_by_role(output_params, 'numerator') or 'errors'
        denominator_path = _find_by_role(output_params, 'denominator') or 'length'
        total_num = 0
        total_den = 0
        for item in items:
            result_obj = _parse_raw_response(item.get('api_raw_response'))
            if not result_obj:
                continue
            num_val = _extract_by_path(result_obj, numerator_path)
            den_val = _extract_by_path(result_obj, denominator_path)
            if num_val is not None and den_val is not None and den_val > 0:
                total_num += num_val
                total_den += den_val
        if total_den == 0:
            return None
        return round(total_num / total_den, 4)
```

#### 配置示例（WER 主维度）

| output 参数 | field_path | output_role | agg_role | visible_in_report |
|------------|------------|-------------|----------|-------------------|
| wer | `wer` | main | value | true |
| errors | `errors` | aux | numerator | false |
| length | `length` | aux | denominator | false |

- **评估时**：`parse_dimension_result` 按 `output_role=main` 的 `field_path` 提取 `dimension_value`（wer 值）
- **聚合时**：`WeightedSumRatioStrategy` 从 `api_raw_response` 按 `agg_role` 提取 errors/length
- **报告展示**：`visible_in_report=false` 的辅助字段不出现在维度列中

---

## 不变部分

- 单条 `update_dimension_result` 不变
- 非多轮场景的状态更新逻辑不变
- `parse_dimension_result` 已改为配置驱动（按 `output_role=main` 的 `field_path` 提取），不再依赖 keywords 兜底

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `25_evaluation_service单轮评估` | 单轮评估产生 round_number 记录 |
| `23_E2E测试结果存储结构` | aggregated 字段写入 |
| `16_API测试结果存储结构` | aggregated 字段写入 |
