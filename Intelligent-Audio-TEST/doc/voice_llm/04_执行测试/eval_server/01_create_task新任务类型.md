# 01 — create_task 新任务类型

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/controllers/api.py`

---

## 背景

eval_server 的 `POST /api/create_task` 端点目前支持 6 种任务类型：`wer`、`ser`、`der`、`cpwer`、`tcpwer`、`stm_wer`。voice_llm 改造需要新增 `bleu` 和 `llm_judge` 两种类型。

---

## 改造内容

### 1. 扩展 SUPPORTED_TASK_TYPES

```python
# api.py 顶部常量
SUPPORTED_TASK_TYPES = [
    'wer', 'ser', 'der', 'cpwer', 'tcpwer', 'stm_wer',
    'bleu',        # 新增
    'llm_judge',   # 新增
]
```

### 2. 新类型字段验证

```python
def create_task():
    data = request.get_json()
    task_type = data.get('task_type')

    if task_type not in SUPPORTED_TASK_TYPES:
        return error_response(
            f'不支持的任务类型: {task_type}',
            CODE_VALIDATION_ERROR, 400
        )

    # 字段验证
    task_params = data.get('task_params', {})

    if task_type in ('wer', 'ser'):
        # 现有验证
        required = ['asr_ref', 'asr_result']
    elif task_type in ('cpwer', 'tcpwer', 'stm_wer'):
        required = ['ref_stm', 'hyp_stm']
    elif task_type == 'der':
        required = ['rttm_ref', 'stm_ref', 'rttm_res', 'stm_res']
    elif task_type == 'bleu':
        # BLEU: hypothesis + reference
        required = ['hypothesis', 'reference']
    elif task_type == 'llm_judge':
        # LLM Judge: hypothesis + reference + model + prompt_template
        required = ['hypothesis', 'reference', 'model', 'prompt_template']

    for field in required:
        if field not in task_params:
            return error_response(
                f'{task_type} 类型缺少必填字段: {field}',
                CODE_VALIDATION_ERROR, 400
            )

    # ... 后续逻辑 ...
```

### 3. BLEU 任务创建

```python
elif task_type == 'bleu':
    # 本地计算（BLEU 计算量较小）
    if can_start_locally():
        task_id = str(uuid.uuid4())
        thread = threading.Thread(
            target=process_local_task,
            args=(task_id, task_type, task_params),
            daemon=True
        )
        thread.start()

        TaskModel.update_task_status(task_id, status='processing')
        return success_response({'task_id': task_id})
```

### 4. LLM Judge 任务创建

```python
elif task_type == 'llm_judge':
    # LLM Judge 需要调用外部 LLM API，超时较长
    # 优先使用远程端点（如果配置了）
    if endpoints:
        result = remote_service.create_remote_task(
            task_type=task_type,
            task_params=task_params,
            endpoints=endpoints,
        )
        return success_response(result)
    else:
        # 无远程端点时本地计算
        task_id = str(uuid.uuid4())
        thread = threading.Thread(
            target=process_local_task,
            args=(task_id, task_type, task_params),
            daemon=True
        )
        thread.start()
        return success_response({'task_id': task_id})
```

### 5. 本地任务处理

```python
def process_local_task(task_id, task_type, task_params):
    """本地任务处理线程"""
    try:
        result = TaskService.calculate(task_type, task_params)
        TaskModel.update_task_status(task_id, status='completed', result=json.dumps(result))
    except Exception as e:
        TaskModel.update_task_status(task_id, status='failed', error_msg=str(e))
```

### 6. 任务类型字段要求汇总

| 类型 | 必填字段 | 可选字段 |
|------|---------|---------|
| `wer` | `asr_ref`, `asr_result` | `source_lang`, `target_lang`, `normalize` |
| `ser` | `asr_ref`, `asr_result` | `source_lang`, `target_lang`, `normalize` |
| `bleu` | `hypothesis`, `reference` | `source_lang`, `target_lang`, `normalize` |
| `llm_judge` | `hypothesis`, `reference`, `model`, `prompt_template` | `max_tokens`, `temperature`, `scoring_criteria` |
| `der` | `rttm_ref`, `stm_ref`, `rttm_res`, `stm_res` | `collar`, `skip_overlap` |

---

## 不变部分

- 现有 6 种类型的验证和处理逻辑不变
- 远程端点选择逻辑不变
- 本地并发管理不变
- 任务轮询接口不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `02_BLEU计算器` | bleu 类型计算实现 |
| `03_LLM_Judge计算器` | llm_judge 类型计算实现 |
| `26_evaluation_api_client适配` (主后端) | 请求发送方 |
