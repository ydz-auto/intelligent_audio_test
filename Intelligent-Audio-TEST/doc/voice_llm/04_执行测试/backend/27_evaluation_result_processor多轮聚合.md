# 27 — evaluation_result_processor 多轮聚合

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/utils/evaluation_result_processor.py`

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
            "avg_bleu": 0.91,
            "avg_llm_judge": 4.2,
            "avg_latency": 1.83,
            "interruption_count": 1,
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

### 6. 聚合策略

| 维度类型 | 聚合方式 | 说明 |
|---------|---------|------|
| WER | 算术平均 | 多轮 WER 取平均 |
| BLEU | 算术平均 | 多轮 BLEU 取平均 |
| LLM Judge | 算术平均 | 多轮 LLM 评分取平均 |
| SER | 加权平均 | 按句子数加权 |
| DER | 加权平均 | 按时长加权 |

---

## 不变部分

- 单次评估的 `parse_dimension_result` 不变
- 单条 `update_dimension_result` 不变
- 非多轮场景的状态更新逻辑不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `25_evaluation_service单轮评估` | 单轮评估产生 round_number 记录 |
| `23_E2E测试结果存储结构` | aggregated 字段写入 |
| `16_API测试结果存储结构` | aggregated 字段写入 |
