# 26 — evaluation_api_client 适配

> **所属步骤**：04_执行测试 → backend  
> **改造类型**：修改  
> **涉及文件**：`backend/utils/evaluation_api_client.py`

---

## 背景

`evaluation_api_client.py` 负责构建发送到 `eval_server` 的 HTTP 请求体。现有请求体格式针对 WER/SER/DER 等标准评估类型设计，需要扩展以支持 `bleu` 和 `llm_judge` 两种新类型，以及多轮对话的数据结构。

---

## 改造内容

### 1. 现有 `build_payload()` 签名

```python
def build_payload(
    self,
    task_type: str,
    algorithm_result: dict,
    ref_texts: dict,
    dim_data: dict,
    **kwargs
) -> dict:
```

### 2. 新增类型分支

```python
def build_payload(self, task_type, algorithm_result, ref_texts, dim_data, **kwargs):
    round_number = kwargs.get('round_number')

    # 如果是多轮评估，提取单轮数据
    if round_number is not None and isinstance(algorithm_result, dict):
        rounds = algorithm_result.get('rounds', [])
        if round_number < len(rounds):
            round_data = rounds[round_number]
            output_text = round_data.get('output', {}).get('asr_text', '')
        else:
            output_text = ''
    else:
        output_text = self._extract_output_text(algorithm_result, dim_data)

    ref_text = self._extract_ref_text(ref_texts, dim_data)

    if task_type == 'wer':
        return self._build_wer_payload(output_text, ref_text, dim_data)
    elif task_type == 'ser':
        return self._build_ser_payload(output_text, ref_text, dim_data)
    elif task_type == 'bleu':
        return self._build_bleu_payload(output_text, ref_text, dim_data)
    elif task_type == 'llm_judge':
        return self._build_llm_judge_payload(output_text, ref_text, dim_data)
    else:
        return self._build_generic_payload(task_type, output_text, ref_text, dim_data)
```

### 3. BLEU payload

```python
def _build_bleu_payload(self, output_text, ref_text, dim_data):
    return {
        'task_type': 'bleu',
        'task_params': {
            'hypothesis': output_text,
            'reference': ref_text,
            'source_lang': dim_data.get('source_lang', 'zh'),
            'target_lang': dim_data.get('target_lang', 'en'),
            'normalize': True,
        }
    }
```

### 4. LLM Judge payload

```python
def _build_llm_judge_payload(self, output_text, ref_text, dim_data):
    api_settings = dim_data.get('api_settings', {})

    return {
        'task_type': 'llm_judge',
        'task_params': {
            'hypothesis': output_text,
            'reference': ref_text,
            'model': api_settings.get('model', 'gpt-4'),
            'prompt_template': api_settings.get('promptTemplate', ''),
            'max_tokens': api_settings.get('maxTokens', 1024),
            'temperature': api_settings.get('temperature', 0.1),
            'scoring_criteria': api_settings.get('scoringCriteria', []),
        }
    }
```

### 5. 通用 fallback payload

```python
def _build_generic_payload(self, task_type, output_text, ref_text, dim_data):
    """未明确适配的类型使用通用结构"""
    return {
        'task_type': task_type,
        'task_params': {
            'hypothesis': output_text,
            'reference': ref_text,
            **dim_data.get('api_settings', {}),
        }
    }
```

### 6. 请求体结构对比

| 类型 | task_type | task_params 关键字段 |
|------|-----------|-------------------|
| WER | `wer` | `asr_ref`, `asr_result`, `source_lang`, `target_lang` |
| SER | `ser` | `asr_ref`, `asr_result`, `source_lang`, `target_lang` |
| BLEU | `bleu` | `hypothesis`, `reference`, `source_lang`, `target_lang` |
| LLM Judge | `llm_judge` | `hypothesis`, `reference`, `model`, `prompt_template`, `max_tokens`, `temperature` |
| DER | `der` | `rttm_ref`, `stm_ref`, `rttm_res`, `stm_res` |

---

## 不变部分

- 现有 WER/SER/DER payload 构建不变
- HTTP 请求方式（POST to eval_server）不变
- 响应解析逻辑不变（由 `EvaluationResultProcessor` 处理）

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_create_task新任务类型` (eval_server) | eval_server 接收端 |
| `24_evaluation_service_llm_judge分发` | 调用方 |
| `25_evaluation_service单轮评估` | 多轮评估参数传递 |
