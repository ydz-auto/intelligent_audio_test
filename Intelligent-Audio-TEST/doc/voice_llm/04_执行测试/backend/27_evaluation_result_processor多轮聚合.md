# 27 — evaluation_result_processor 多轮聚合

> **所属步骤**：04_执行测试 → backend
> **改造类型**：修改
> **涉及文件**：`backend/services/evaluation/evaluation_result_processor.py`、`backend/services/evaluation/round_aggregator.py`、`backend/utils/report/aggregation_strategies.py`、`backend/utils/report/report_utils.py`

---

## 背景

voice_llm 多轮对话中，每轮独立评估会产生多条 `TestResultDimension` 记录（每条带 `round_number`，0-indexed）。整体评估（`round_number=None`）则产生 `round_number IS NULL` 的记录。

聚合相关逻辑分三层：

| 层 | 文件 | 职责 |
|----|------|------|
| 结果处理 | `evaluation_result_processor.py` | 解析 API 响应、计算得分、更新维度记录、更新 TaskCase 状态 |
| 多轮聚合 | `round_aggregator.py`（`RoundAggregator`） | 按轮聚合维度分数、写 `algorithm_result.aggregated` |
| 报告统计 | `aggregation_strategies.py` + `report_utils.py` | 报告层按 `Dimension.statistic_method` 配置聚合 |

`EvaluationResultProcessor` 继承 `RoundAggregator`，对外保持原有接口不变。

---

## 类结构

```python
class EvaluationResultProcessor(RoundAggregator):
    """
    评估结果处理器，负责解析API响应、计算分数并更新数据库

    继承 RoundAggregator 获取多轮聚合能力，对外保持原有接口不变。
    """
```

---

## 改造内容

### 1. `RoundAggregator.is_multi_round_result()`

```python
def is_multi_round_result(self, result_id):
    """
    Check if a test result contains multi-round evaluation data.

    Returns True if any TestResultDimension has round_number set.
    """
    # 查询条件：
    # TestResultDimension.test_result_id == result_id
    # TestResultDimension.round_number.isnot(None)
    # → 命中任意一条即视为多轮结果
```

### 2. `RoundAggregator.check_all_round_dimensions_completed()`

```python
def check_all_round_dimensions_completed(self, result_id):
    """
    Check if all dimension evaluations in a multi-round result are done.

    Returns True when no TestResultDimension is still in 'pending' status.
    """
    # 查询条件：
    # TestResultDimension.test_result_id == result_id
    # TestResultDimension.evaluation_status == 'pending'
    # → pending_count == 0 即全部完成
```

> **注意**：状态字段是 `evaluation_status`（评估状态），不是 `status`（执行状态）。两字段并存：
> - `status`：维度执行状态（成功/失败标记）
> - `evaluation_status`：评估状态流转 `pending → queued → running/calculating → completed/failed`

### 3. `RoundAggregator.aggregate_round_results()`

```python
def aggregate_round_results(self, result_id, task_id, test_case_id):
    """
    Aggregate multi-round evaluation results into per-dimension averages.

    Queries all TestResultDimension records (round_number IS NOT NULL) for the given result_id,
    groups them by dimension name, computes arithmetic mean scores,
    writes the aggregated data to TestResult.algorithm_result['aggregated'],
    and creates round_number=NULL TestResultDimension records for the overall scores.

    Returns:
        dict with keys like avg_{dim_name}, round_count, completed_rounds
    """
```

#### 核心逻辑（按真实代码）

```python
# 1. 仅查询单轮维度记录（排除整体记录，避免自引用）
dim_results = query(TestResultDimension).filter(
    TestResultDimension.test_result_id == result_id,
    TestResultDimension.round_number.isnot(None),
).all()

# 2. 按维度名分组（通过 dimension_id 反查 Dimension 表取 name）
#    同时记录 dim_info: {dimension_id, algorithm_type}
dim_groups[dim_name].append({
    'round_number': dr.round_number,
    'score': dr.score,
    'raw_value': dr.dimension_value,
    'evaluation_status': dr.evaluation_status,
})

# 3. 逐维度计算算术平均（非加权）
completed = [r for r in results
             if r['evaluation_status'] == 'completed' and r['score'] is not None]
if completed:
    avg_score = sum(r['score'] for r in completed) / len(completed)
    aggregated[f'avg_{dim_name}'] = round(avg_score, 4)
    # avg_raw：dimension_value 的算术平均（仅对 raw_value 非 None 的轮次）
else:
    aggregated[f'avg_{dim_name}'] = None
```

#### round_number=NULL 整体维度记录的创建/兜底语义（关键）

对每个有完成轮次的维度，查找 `round_number IS NULL` 的整体记录：

```python
existing_overall = query(TestResultDimension).filter(
    TestResultDimension.test_result_id == result_id,
    TestResultDimension.dimension_id == info.get('dimension_id'),
    TestResultDimension.round_number.is_(None),
).first()

if existing_overall:
    # 已有整体评估记录（由 round_number=None 的整体评估产生），不覆盖其分数
    # 仅在整体评估未产生分数时用算术平均兜底
    if existing_overall.score is None:
        existing_overall.score = round(avg_score, 4)
        existing_overall.dimension_value = round(avg_raw, 4) if avg_raw is not None else None
        existing_overall.evaluation_status = 'completed'
else:
    # 没有整体评估记录，创建一条聚合记录
    overall_dim = TestResultDimension(
        test_result_id=result_id,
        dimension_id=info.get('dimension_id'),
        algorithm_type=info.get('algorithm_type'),
        round_number=None,
        score=round(avg_score, 4),
        dimension_value=round(avg_raw, 4) if avg_raw is not None else None,
        status=None,
        evaluation_status='completed',
        error_message=None,
    )
    add(overall_dim)
```

**语义总结**：

| 场景 | 行为 |
|------|------|
| 整体评估已产生分数 | **不覆盖**（LLM Judge 等整体评估分数优先） |
| 整体记录存在但 score 为 NULL | 用算术平均兜底回填 |
| 整体记录不存在 | 创建一条聚合记录（evaluation_status='completed'） |

#### 统计字段与写回

```python
aggregated['round_count'] = len(set(
    r.round_number for r in dim_results if r.round_number is not None
))
aggregated['completed_rounds'] = len(set(
    r.round_number for r in dim_results
    if r.round_number is not None and r.evaluation_status == 'completed'
))

self._update_algorithm_result_aggregated(local_db_session, result_id, aggregated)
local_db_session.commit()
```

### 4. `_update_algorithm_result_aggregated()`（合并写入，非覆盖）

```python
def _update_algorithm_result_aggregated(self, db_session, result_id, aggregated):
    """Write aggregated results into TestResult.algorithm_result['aggregated']."""
    test_result = db_session.query(TestResult).filter(TestResult.id == result_id).first()
    if not test_result:
        return

    result_data = test_result.algorithm_result
    # 循环反序列化，处理可能的双重序列化旧数据
    while isinstance(result_data, str):
        try:
            result_data = json.loads(result_data)
        except (json.JSONDecodeError, TypeError):
            result_data = {}

    # 合并到已有的 aggregated，而非覆盖
    existing_aggregated = result_data.get('aggregated', {})
    existing_aggregated.update(aggregated)
    result_data['aggregated'] = existing_aggregated
    test_result.algorithm_result = result_data
```

合并语义与 `E2EAggregator.build_algorithm_result` 产生的初始骨架兼容：

```json
{
  "test_type": "e2e",
  "algorithm_type": "...",
  "total_rounds": 3,
  "rounds": [...],
  "aggregated": {
    "avg_latency": 1.2345,
    "avg_wer": null,
    "avg_llm_judge": null
  }
}
```

- `avg_latency`：执行阶段直接计算
- `avg_wer` / `avg_llm_judge`：初始为 null 占位，由评估聚合回填（本文件 `avg_{dim_name}` 键，如 `avg_词错率`）

### 5. 当前调用状态（重要）

`aggregate_round_results()` / `is_multi_round_result()` / `check_all_round_dimensions_completed()` 当前**无生产调用方**，作为多轮聚合能力保留。

实际生效的分数回填路径：

| 路径 | 位置 | 说明 |
|------|------|------|
| 单轮评估分数回填 | `e2e_aggregator.py` → `update_algorithm_result_evaluation()` | 从 DB 查 `round_number` 非 NULL 的 `TestResultDimension`，按轮回填到 `algorithm_result.rounds[].evaluation` |
| 整体评估分数 | `round_number=None` 的整体评估 | 直接产生 `round_number IS NULL` 的 `TestResultDimension` 记录 |
| 报告层聚合 | `report_utils.py` + `aggregation_strategies.py` | 按 `statistic_method` 配置聚合 |

### 6. `update_task_case_status()`（真实实现）

判定所有 TestResult 的维度评估都完成后，更新 TaskCase 最终状态：

```python
def update_task_case_status(self, result_id, current_result_all_completed,
                            task_id, test_case_id, test_type=None):
```

核心流程：

```python
# 1. 预期结果数量
if task.type == 'e2e':
    expected_count = count(TaskDevice.filter_by(task_id=task_id))
else:
    expected_count = count(TaskAPI.filter_by(task_id=task_id))
if expected_count == 0:
    expected_count = 1  # 兜底

# 2. 预期维度总数（去重合并两处配置）
#    - rounds[].evaluation.dimensions  （单轮维度）
#    - config.dimensions               （多轮聚合维度）
#    去重后仅统计数据库中启用（Dimension.status == True）且存在的维度
expected_dim_count = query(Dimension).filter(
    Dimension.id.in_(unique_dim_ids), Dimension.status == True
).count()

# 3. 数量检查：结果未全 / 维度未全 → 直接 return 继续等待
if len(all_results) < expected_count: return
if len(dims) < expected_dim_count: case_all_finished = False

# 4. 逐维度检查评估状态
for dim in dims:
    if dim.evaluation_status in ['pending', 'running', 'queued', 'calculating']:
        res_finished = False   # 仍在进行中
    if dim.evaluation_status == 'failed':
        res_failed = True      # 任一维度失败 → 该结果失败

# 5. 全部完成才更新最终状态
new_status = 'failed' if case_any_failed else 'completed'
update_task_case_status_in_db(local_db_session, task_id, test_case_id,
                              new_status, new_evaluation_status)

# 6. Task 处于 evaluating 过渡态时更新为最终状态，并强制推送进度
if task.status == 'evaluating':
    task.status = new_status
    execution_engine._emit_progress(task, force=True)
```

### 7. 其他配套方法

| 方法 | 说明 |
|------|------|
| `mark_test_result_completed(result_id)` | 无评估维度场景：TestResult.execution_status 置 `completed` + 预提取 algorithm_results 快照 |
| `update_dimension_result(...)` | 更新单条维度记录（dimension_value/score/status/evaluation_status/error_message/api_raw_response/api_request_body）；dimension_value 为 double 类型，非数值转 None |
| `update_dimension_result_failed / _completed` | 失败/成功快捷封装（status 与 evaluation_status 同步置 failed/completed） |
| `process_group_dimension_results(...)` | 整组维度解析打分 → 提取 `output_role=aux` 且 `visible_in_report=true` 的辅助字段写入 `result_data.evaluation_data`（大字段走 result_data 文件）→ 预提取 algorithm_results → `check_all_dimensions_completed` 通过则调用 `update_task_case_status` |
| `check_all_dimensions_completed(result_id)` | 该结果所有维度 `evaluation_status` 均不在 `['pending','running','queued','calculating']` |
| `_build_and_store_algorithm_results(...)` | 预提取 algorithm_results 扁平列表存入 `result_data['algorithm_results']`，报告页/详情页直接读取 |

---

## 聚合策略（报告层，配置驱动 + 策略模式）

> **注意**：策略模式用于**报告统计层**（`report_utils.py` 调用），不作用于 `RoundAggregator.aggregate_round_results`（后者固定算术平均）。

聚合方式通过 `Dimension.statistic_method` 字段配置（DB 列默认 `average`），由 `AggregationStrategy` 策略类统一调度，新增聚合方式只需实现接口并注册到 registry。

#### 策略注册表

| statistic_method | 策略类 | 说明 |
|-----------------|--------|------|
| `average` | `SimpleAverageStrategy` | 简单算术平均（默认） |
| `weighted_wer` | `WeightedSumRatioStrategy` | 加权 WER = Σerrors / Σlength |
| `pass_rate` | `PassRateStrategy` | 达标率 = 达标用例数 / 总用例数（配合 `pass_threshold`） |

#### 策略接口与注册

```python
class AggregationStrategy(ABC):
    @abstractmethod
    def aggregate(self, items: List[Dict[str, Any]], output_params: List[Dict[str, Any]] = None) -> Optional[float]:
        pass

_REGISTRY: Dict[str, AggregationStrategy] = {
    'average': SimpleAverageStrategy(),
    'weighted_wer': WeightedSumRatioStrategy(),
    'pass_rate': PassRateStrategy(),
}

def get_strategy(statistic_method: str) -> AggregationStrategy:
    """按 statistic_method 值获取策略，未知则回退到简单平均。"""
    return _REGISTRY.get(statistic_method, _REGISTRY['average'])
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

- 单条 `update_dimension_result` 接口不变
- 非 multi-round 场景的状态更新逻辑不变
- `parse_dimension_result` 配置驱动，提取优先级：`output_role=main` 的 `field_path` → 兼容旧字段 `output_field_path` → `api_settings.response_mapping` → 维度名兜底，不再依赖 keywords 兜底

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `25_evaluation_service单轮评估` | 单轮评估产生 round_number 记录 |
| `23_E2E测试结果存储结构` | aggregated 字段写入、rounds[].evaluation 回填 |
| `16_API测试结果存储结构` | aggregated 字段写入 |
