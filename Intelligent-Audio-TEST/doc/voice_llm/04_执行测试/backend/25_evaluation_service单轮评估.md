# 25 — evaluation_service 评估编排

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/services/evaluation/evaluation_service.py`
> **关联类**：`EvaluationService(EvaluationLoggerMixin)`

---

## 背景

多轮对话（用例配置了 `rounds`）中，每轮可以配置独立的评估（`rounds[i].evaluation`）。`evaluate_case()` 需要支持两种粒度：

| 粒度 | round_number | 语义 |
|------|-------------|------|
| 整体评估 | `None` | 取顶层 `config.dimensions`，对最后一轮结果（rounds[-1]）评估 |
| 单轮评估 | `0`、`1`... | 只取 `rounds[i].evaluation.dimensions`，对该轮结果评估 |

触发条件由 `base_executor._evaluate_result` 控制（见 `28_base_executor评估入队适配`），不在此类中判断。

---

## 类结构

- 继承 `EvaluationLoggerMixin`，统一 `_log` 日志能力
- 组合 `evaluationApiClient`（HTTP 请求 + Payload 构建）
- 组合 `EvaluationResultProcessor`（结果解析/算分）
- 组合 `EndpointWorker`（每个评估端点一个常驻 Worker，内部队列 + 并发消费）

```python
class EvaluationService(EvaluationLoggerMixin):
    def __init__(self):
        self.api_client = evaluationApiClient()
        self.result_processor = EvaluationResultProcessor()
        self.endpoint_workers = {}      # endpoint_url -> EndpointWorker
        self.endpoint_workers_lock = Lock()
        ...
        self._load_all_endpoint_configs()   # 启动时从 Dimension 表预创建 Worker
        self.api_client.init_thread_pool()
```

全局单例：`evaluation_service = EvaluationService()`。

---

## evaluate_case 入口（kwargs 驱动）

实际签名（不是位置参数列表，round_number 走 kwargs）：

```python
def evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **kwargs):
```

kwargs 关键键：

| 键 | 来源 | 说明 |
|----|------|------|
| `test_type` | 执行器传参 | `'api'` / `'device'` |
| `round_number` | 执行器传参 | `None`=整体评估，`0`起=单轮评估 |
| `reference_params_col` | 执行器传参 | 参考参数独立列名（1-indexed 取轮） |
| `algorithm_type` | 执行器传参 | 默认 `'translation'` |
| `rounds` | 本方法内部构建 | rounds_list 列表 |

### 主流程

```mermaid
flowchart TD
    A[evaluate_case] --> B[读 TestCase.algorithm_params 独立列]
    B --> C{algorithm_result.rounds 存在?}
    C -- 是 --> D[_build_rounds_list 构建 rounds 列表]
    D --> E{round_number 指定?}
    E -- 是 --> F[rounds_list 截取单轮]
    E -- 否 --> G[rounds_list 全量]
    F --> H
    G --> H[_load_test_case_and_refs\nround_number!=None 只取该轮 dims\nNone 只取顶层 config.dimensions]
    H --> I{有维度?}
    I -- 否 --> J[mark_test_result_completed + _post_evaluate_updates\n返回 False]
    I -- 是 --> K[_load_dimension_data\nDB 加载维度 + output/input 参数\n子维度继承父维度配置]
    K --> L[_mark_evaluation_queued]
    L --> M[_create_dimension_results\n按 result_id+dim_id+round_number 去重复用]
    M --> N[_dispatch_evaluation_tasks\n按 (endpoint_url, parent_id) 分组]
    N --> O[thread_pool.submit → EndpointWorker 队列]
    O --> P[返回 True，不等待评估完成]
```

### 关键分支说明

1. **rounds_list 构建**：`_build_rounds_list` 遍历 `param_mappings`（按 algorithm_type 从配置加载），按 `source` 取数：
   - `device/api`：从 `algo_result.rounds[i].output` 取（key 是 target_param 名）
   - `reference`：按轮从 reference_params_col 独立列加载（`round_number + 1`，因为列是 1-indexed）
   - `case`：按轮从 algorithm_params_col 独立列加载（同样 1-indexed）
   - 用 `None` 而非 `''` 做默认值，避免空串覆盖维度级默认值

2. **维度范围**（`_load_test_case_and_refs`）：
   - 单轮评估：只取 `rounds[round_number].evaluation.dimensions`
   - 整体评估：只取顶层 `config.dimensions`
   - 内部按 `dim_id` 去重

3. **无维度短路**：`_extract_dimension_ids` 为空 → 记录日志 → `mark_test_result_completed(result_id)` → `_post_evaluate_updates` → 返回 False。

---

## 关键方法明细

### 1. _extract_round_eval_data（单轮扁平字段提取）

```python
def _extract_round_eval_data(self, algorithm_result, round_number):
    # 循环反序列化，处理可能的双重序列化旧数据
    while isinstance(algorithm_result, str):
        algorithm_result = json.loads(algorithm_result)   # 失败返回 None
    ...
    rounds = algorithm_result.get('rounds', [])
    if not rounds or round_number >= len(rounds):
        return None
    round_data = rounds[round_number]
    output = round_data.get('output', {})
    flat = dict(output) if isinstance(output, dict) else {}
    if 'latency' in round_data:
        flat['latency'] = round_data['latency']
    return flat
```

- 返回**扁平结构**：把 `rounds[i].output` 的字段整体提升到顶层（如 `answer`/`correct_answer`/`asr_text` 等），不再做字段名硬编码
- 轮次不存在（越界/无 rounds）返回 `None`

### 2. _build_rounds_list（算法参数映射）

用于把 `algo_result.rounds[]` 转换成评估端点能消费的 `[{reference, hypothesis, ...}]` 列表，key 统一为 `target_param`（映射配置决定）。

### 3. _load_test_case_and_refs

加载 `TestCase`、`algorithm_type`（DB 优先，兜底 kwargs）、`ref_texts`（从 kwargs 按 `eval_input_fields` 提取，key 含 `rttm_ref/stm_ref/asr_ref/asr_rerference_text`）、`dimensions_config`（按 round_number 分流）。

### 4. _load_dimension_data（含子维度继承）

- 一次查询 `Dimension`（status==True），预加载全部 `EvaluationDimensionParam`（output/input 方向），避免 N+1
- `output_field_path` 只从 `output_role='main'` 且非空 `field_path` 的参数取，避免误取 aux 字段
- **子维度继承**：
  - 无有效 `api_endpoints`/`api_url` 时继承父维度的 `api_endpoints/api_url/api_settings`
  - 继承父维度 `task_type_code` 为 `parent_task_type_code`（发请求时 task_type 用它）
  - 自己无 `input_params` 时继承父维度 input_params
  - `task_type_code` 不继承（各子维度独立，发请求时作为 sub_tasks 注入）

### 5. _create_dimension_results（去重复用）

按 `(test_result_id, dimension_id, round_number)` 查重：

- `round_number` 有值 → 过滤 `round_number == round_number`；无值 → 过滤 `round_number IS NULL`
- 已存在：
  - `evaluation_status == 'pending'`：直接复用
  - 否则：重置为 `pending`（score/error_message/api_request_body/api_raw_response 清空）
- 不存在：创建记录 `status=None, evaluation_status='pending'`

### 6. _dispatch_evaluation_tasks（端点分组）

- 分组建 key：`(endpoint_url, parent_id)`
  - 主维度：`parent_id = 自身 id`
  - 子维度：`parent_id = parent_dimension_id`（同一父维度的子维度合一个请求）
- endpoint_url：优先 `api_endpoints[0]`（`get_endpoint_url`），兜底 `api_url`
- 无端点的维度：走 `update_all_dimensions_in_group_failed` 标记失败 + `_post_evaluate_updates`，避免任务卡死
- task_type：用 `parent_task_type_code or task_type_code`
- 提交：`api_client.thread_pool.submit(_submit_to_endpoint_worker, task_data, worker)`

### 7. _build_task_data（payload 字段透传）

```python
idx = round_number if round_number is not None else -1   # 整体评估取 rounds[-1]
```

- 透传 `round_number`（仅多轮）、`rounds`（仅多轮）、扁平字段（单轮兼容 answer 等）
- `algo_results`（output_field_keys）：先取 `algorithm_result.get(key)`，None 时从 `ref_output`（rounds[idx].output）补齐
- 透传 `ref_texts` 各字段

### 8. _post_evaluate_updates（状态同步）

- TaskCase：`evaluation_status in ['queued','pending']` 且 `execution_status in ['completed','failed']` → 置 `completed`，`status=='pending'` 同步为 execution_status
- Task 统计：更新 `completed_cases/failed_cases`
- Task 过渡态：`task.status=='evaluating'` 且无 `running/calculating/queued/pending` 用例 → 最终状态 `failed if failed_cases>0 else completed` + `completed_at`
- 通知：`execution_engine._emit_progress(task, force=True)` + `execution_engine.notify_case_completed(task_id)`

---

## 状态字段

`TestResultDimension` 记录：

| 字段 | 初始值 | 流转 |
|------|-------|------|
| `status` | `None` | 维度执行状态（见 27 文档） |
| `evaluation_status` | `pending` | `queued → running/calculating → completed/failed` |
| `round_number` | `None` / 轮次号 | 单轮评估标记轮次，整体评估为 NULL |

创建维度记录时使用 `round_number` 入参（`status=None, evaluation_status='pending'`）。

---

## E2E 中的触发方式

评估的触发不在本类中判断，由执行器 `_evaluate_result` 完成（见 `28_base_executor评估入队适配`）：

- 单轮评估触发：`rounds[i].evaluation.enabled` 双检查（`enabled` 且 `dimensions` 非空，snake_case）
- 整体评估触发：顶层 `config.dimensions` 非空时提交 `round_number=None`

前端 `rounds[i].evaluation` 配置项 snake_case 命名见 `28_base_executor评估入队适配` 的命名注意表。

---

## 不变部分

- 评估结果解析/算分/聚合逻辑不变（见 `27_evaluation_result_processor多轮聚合`）
- 无 `rounds` 的用例：`algorithm_result.get('rounds')` 为假 → 不构建 rounds_list，走整体评估路径
- 端点 Worker 请求执行与并发控制逻辑不变（见 `26_evaluation_api_client适配`）

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `28_base_executor评估入队适配` | `_evaluate_result(round_number=...)` 入队 |
| `27_evaluation_result_processor多轮聚合` | 评估结果处理与多轮聚合 |
| `26_evaluation_api_client适配` | HTTP 请求 / Payload 构建 / 端点并发 |
| `30_execution_engine多轮进度` | `_emit_progress` / `notify_case_completed` |