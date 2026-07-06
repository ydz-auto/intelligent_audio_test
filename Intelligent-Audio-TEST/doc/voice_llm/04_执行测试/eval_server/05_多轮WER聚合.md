# 05 — 多轮 WER 聚合

> **所属步骤**：04_执行测试 → eval_server  
> **改造类型**：修改  
> **涉及文件**：`eval_server/app/services/wer_calculator.py`、`eval_server/app/services/task_service.py`

---

## 背景

voice_llm 多轮对话中，每轮独立计算 WER 后需要聚合为全局 WER。当前 eval_server 仅支持单文本对的 WER 计算。改造需要新增多轮 WER 聚合计算模式。

---

## 改造内容

### 1. 新增 `calculate_multi_round_wer()` 函数

```python
def calculate_multi_round_wer(
    rounds: list[dict],
    source_lang: str = 'zh',
    target_lang: str = 'en',
    normalize: bool = True,
) -> dict:
    """
    多轮 WER 聚合计算。

    Args:
        rounds: 每轮的 reference 和 hypothesis
            [
                {"reference": "ref text 1", "hypothesis": "hyp text 1"},
                {"reference": "ref text 2", "hypothesis": "hyp text 2"},
                ...
            ]
        source_lang: 源语言
        target_lang: 目标语言
        normalize: 是否标准化

    Returns:
        {
            "wer": 0.05,
            "per_round": [
                {"round": 0, "wer": 0.03, "errors": 1, "length": 30},
                {"round": 1, "wer": 0.08, "errors": 3, "length": 35},
                ...
            ],
            "aggregated": {
                "total_errors": 5,
                "total_length": 100,
                "weighted_wer": 0.05
            }
        }
    """
    per_round = []
    total_errors = 0
    total_length = 0

    for idx, round_data in enumerate(rounds):
        ref = round_data.get('reference', '')
        hyp = round_data.get('hypothesis', '')

        result = calculate_wer(
            ref_text=ref,
            hyp_text=hyp,
            source_lang=source_lang,
            target_lang=target_lang,
            normalize=normalize,
        )

        round_info = {
            'round': idx,
            'wer': result['wer'],
            'errors': result.get('errors', 0),
            'length': result.get('length', 0),
            'insertions': result.get('insertions', 0),
            'deletions': result.get('deletions', 0),
            'substitutions': result.get('substitutions', 0),
        }
        per_round.append(round_info)

        total_errors += round_info['errors']
        total_length += round_info['length']

    # 加权平均 WER
    weighted_wer = total_errors / total_length if total_length > 0 else 0
    # 简单平均 WER
    simple_wer = sum(r['wer'] for r in per_round) / len(per_round) if per_round else 0

    return {
        'wer': round(weighted_wer, 4),
        'per_round': per_round,
        'aggregated': {
            'total_errors': total_errors,
            'total_length': total_length,
            'weighted_wer': round(weighted_wer, 4),
            'simple_wer': round(simple_wer, 4),
            'round_count': len(per_round),
        },
        'source_lang': source_lang,
        'target_lang': target_lang,
    }
```

### 2. 注册到 TaskService

```python
# task_service.py
from app.services.wer_calculator import calculate_wer, calculate_multi_round_wer

class TaskService:
    @classmethod
    def calculate(cls, task_type, task_params):
        if task_type == 'wer':
            # 检查是否为多轮模式
            if 'rounds' in task_params:
                return calculate_multi_round_wer(
                    rounds=task_params['rounds'],
                    source_lang=task_params.get('source_lang', 'zh'),
                    target_lang=task_params.get('target_lang', 'en'),
                    normalize=task_params.get('normalize', True),
                )
            else:
                # 现有单轮逻辑
                return calculate_wer(...)
```

### 3. 请求体格式

```json
{
  "task_type": "wer",
  "task_params": {
    "rounds": [
      {"reference": "你好世界", "hypothesis": "你好世界"},
      {"reference": "今天天气不错", "hypothesis": "今天天气很好"}
    ],
    "source_lang": "zh",
    "target_lang": "en",
    "normalize": true
  }
}
```

### 4. 单轮 vs 多轮区分

```python
def calculate(cls, task_type, task_params):
    if task_type == 'wer':
        if 'rounds' in task_params:
            # 多轮模式
            return calculate_multi_round_wer(**task_params)
        elif 'asr_ref' in task_params and 'asr_result' in task_params:
            # 现有单轮模式
            return calculate_wer(
                ref_text=task_params['asr_ref'],
                hyp_text=task_params['asr_result'],
                ...
            )
```

---

## 不变部分

- 现有 `calculate_wer()` 函数签名和逻辑不变
- 单轮 WER 请求格式不变
- 其他计算器（SER/DER/CPWER）不变

---

## 补充：与主后端聚合策略对齐

eval_server 负责单轮 WER 计算，返回 `wer`、`errors`、`length` 等字段。多轮聚合由主后端的 `aggregation_strategies.py` 完成。

### 主后端聚合配置

主后端通过 `Dimension.statistic_method` 字段配置聚合方式：

| statistic_method | 策略类 | 说明 |
|-----------------|--------|------|
| `average` | `SimpleAverageStrategy` | 简单算术平均 |
| `weighted_wer` | `WeightedSumRatioStrategy` | 加权 WER = Σerrors / Σlength |

### 数据流

```
eval_server 单轮返回: {wer: 0.15, errors: 3, length: 20}
                          ↓
主后端 TestResultDimension 存储:
  dimension_value = 0.15 (按 output_role=main 的 field_path 提取)
  api_raw_response = {wer:0.15, errors:3, length:20} (完整响应)
                          ↓
主后端报告聚合:
  WeightedSumRatioStrategy 从 api_raw_response 按 agg_role 提取:
    numerator = errors (agg_role=numerator)
    denominator = length (agg_role=denominator)
  = Σerrors / Σlength
```

### eval_server 返回字段与主后端 output 参数映射

| eval_server 返回字段 | 主后端 output 参数配置 | |
|---------------------|----------------------|---|
| | output_role | agg_role |
| `wer` | main | value |
| `errors` | aux | numerator |
| `length` | aux | denominator |

> eval_server 不需要关心聚合策略，只负责单轮计算并返回所有字段。聚合由主后端按配置驱动完成。

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_create_task新任务类型` | 任务入口 |
| `27_evaluation_result_processor多轮聚合` (主后端) | 结果处理 |
