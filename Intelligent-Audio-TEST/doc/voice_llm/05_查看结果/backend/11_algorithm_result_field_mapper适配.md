# 11 - algorithm_result_field_mapper 适配

## 涉及文件
- `Intelligent-Audio-TEST/backend/algorithm/algorithm_result_field_mapper.py`

## 现状分析

`AlgorithmResultFieldMapper` 负责将 API 返回的原始结果映射为标准的输出字段。

核心方法：
- `map_api_results(algorithm_type, raw_results)` — 映射 API 结果
- `get_output_fields(algorithm_type)` — 获取输出字段定义

现有算法的输出字段：
- translation: `translated_text`, `translation_latency`
- asr: `asr_text`, `asr_rttm`, `asr_latency`
- tts: `tts_audio`, `tts_latency`

## 改造方案

### voice_llm 输出字段（区分 API / E2E）

> **字段来源**：voice_llm 的字段从用例 config 中每轮 `algorithmParams` 提取，不在 `AlgorithmResultFieldMapper` 单独定义"输出字段"。
> 评估时通过 `CaseParameterExtractor.convert_params_to_dict(round.algorithmParams)` 拿到 `{field_code: field_value}`，
> 再按 `algorithm_api_params` (direction=input) 路由到请求体中。

```python
def get_output_fields(self, algorithm_type, test_type=None):
    """获取输出字段定义 — voice_llm 由 rounds 数组承载每轮结果，区分 API / E2E"""
    if algorithm_type == 'voice_llm':
        if test_type == 'e2e':
            return {
                'test_type': {
                    'type': 'text',
                    'description': '测试类型 (e2e)',
                    'required': True
                },
                'algorithm_type': {
                    'type': 'text',
                    'description': '算法类型',
                    'required': True
                },
                'session_id': {
                    'type': 'text',
                    'description': '会话 ID',
                    'required': False
                },
                'rail_distance': {
                    'type': 'number',
                    'description': '导轨距离(cm)',
                    'required': True
                },
                'voiceprint_registered': {
                    'type': 'boolean',
                    'description': '声纹是否注册成功',
                    'required': True
                },
                'total_rounds': {
                    'type': 'number',
                    'description': '总轮次数',
                    'required': True
                },
                'rounds': {
                    'type': 'json',
                    'description': '轮次结果数组，每轮 round/input/output/evaluation/interruption',
                    'required': True
                },
                'aggregated': {
                    'type': 'json',
                    'description': '多轮聚合指标 (avg_wer, avg_bleu, avg_llm_judge, avg_latency, interruption_count)',
                    'required': False
                }
            }
        else:  # api
            return {
                'session_id': {
                    'type': 'text',
                    'description': '会话 ID',
                    'required': True
                },
                'round_count': {
                    'type': 'number',
                    'description': '轮次数',
                    'required': True
                },
                'total_latency': {
                    'type': 'number',
                    'description': '总会话延迟(ms)',
                    'required': False
                },
                'context_mode': {
                    'type': 'text',
                    'description': '上下文模式',
                    'required': False
                },
                'history_count': {
                    'type': 'number',
                    'description': '历史轮数',
                    'required': False
                },
                'error': {
                    'type': 'text',
                    'description': '错误信息',
                    'required': False
                },
                'rounds': {
                    'type': 'json',
                    'description': '完整会话轮次数据，每轮 roundNumber/input/output/latency/round_evaluation',
                    'required': True
                }
            }
    # ... 现有逻辑
```

### map_api_results

```python
def map_api_results(self, algorithm_type, raw_results, test_type=None):
    """映射 API 结果"""
    if algorithm_type == 'voice_llm':
        return self._map_voice_llm_results(raw_results, test_type)
    # ... 现有逻辑

def _map_voice_llm_results(self, raw_results, test_type=None):
    """voice_llm 结果映射 — 区分 API / E2E"""
    if test_type == 'e2e':
        return {
            'test_type': raw_results.get('test_type', 'e2e'),
            'algorithm_type': raw_results.get('algorithm_type', 'voice_llm'),
            'session_id': raw_results.get('session_id'),
            'rail_distance': raw_results.get('rail_distance', 50),
            'voiceprint_registered': raw_results.get('voiceprint_registered', False),
            'total_rounds': raw_results.get('total_rounds', 0),
            'rounds': raw_results.get('rounds', []),
            'aggregated': raw_results.get('aggregated', {}),
        }
    else:  # api
        return {
            'session_id': raw_results.get('session_id', ''),
            'round_count': raw_results.get('round_count', 0),
            'total_latency': raw_results.get('total_latency', 0),
            'context_mode': raw_results.get('context_mode', ''),
            'history_count': raw_results.get('history_count', 0),
            'error': raw_results.get('error'),
            'rounds': raw_results.get('rounds', []),
        }
```

### 从 algorithm_result JSON 提取多轮结果

```python
def extract_round_results(self, algorithm_result, test_type=None):
    """从存储的 algorithm_result 中提取多轮结果 — 区分 API / E2E"""
    if not algorithm_result:
        return []

    rounds = algorithm_result.get('rounds', [])
    is_e2e = test_type == 'e2e' or algorithm_result.get('test_type') == 'e2e'

    if is_e2e:
        return [
            {
                'round_number': r.get('round', 0),           # 0-indexed
                'input_audio_name': r.get('input', {}).get('audio_name', ''),
                'input_audio_path': r.get('input', {}).get('audio_path', ''),
                'input_type': r.get('input', {}).get('type', ''),
                'asr_text': r.get('output', {}).get('asr_text', ''),
                'device_raw': r.get('output', {}).get('device_raw'),
                'latency': r.get('latency', 0),
                'wait_time': r.get('wait_time'),
                'interruption': r.get('interruption'),
                'evaluation': r.get('evaluation', {}),        # E2E 用 evaluation
            }
            for r in rounds
        ]
    else:  # api
        return [
            {
                'round_number': r.get('roundNumber', 1) - 1,  # 1-indexed → 0-indexed
                'input_text': r.get('input', {}).get('text', ''),
                'llm_response': r.get('output', ''),           # output 是 string
                'latency': r.get('latency', 0),
                'response_metrics': r.get('response_metrics', {}),
                'round_evaluation': r.get('round_evaluation', {}),  # API 用 round_evaluation
            }
            for r in rounds
        ]
```

### 与评估的协作

```python
# 单轮评估：提取特定轮次结果
round_results = mapper.extract_round_results(algorithm_result, test_type)
round_0_data = next((r for r in round_results if r['round_number'] == 0), None)

# 整体评估：使用所有轮次
all_rounds = mapper.extract_round_results(algorithm_result, test_type)

# API 结果没有顶层 aggregated，需从 rounds 中计算或由后端补充
if test_type != 'e2e' and not algorithm_result.get('aggregated'):
    aggregated = compute_aggregated_from_rounds(all_rounds, eval_key='round_evaluation')
```

### 算法参数从 config.rounds 提取

执行时通过 `CaseParameterExtractor` 从 `rounds[idx].algorithmParams` 提取输入参数：

```python
# 调用方（APIExecutor / E2EExecutor 内部）
from utils.case_parameter_extractor import CaseParameterExtractor

for round_idx, round_cfg in enumerate(case_config.get('rounds', [])):
    # algorithmParams: [{field_code, field_value}] → dict
    algo_params = CaseParameterExtractor.convert_params_to_dict(
        round_cfg.get('algorithmParams', [])
    )
    # algo_params = { 'inputText': '...', 'railDistance': '50', 'volumeLevel': '70', ... }
```

> **不再用 `algorithm_params` 独立列**：所有算法参数统一在 `rounds[].algorithmParams` 中，无需在 mapper 中按"输出字段"再列举。

## 相关文档
- [08_field_mapper_voice_llm映射.md](08_field_mapper_voice_llm映射.md) — 字段定义
- [backend/api-executor/16_API测试结果存储结构.md](../api-executor/16_API测试结果存储结构.md) — 存储结构
- [02_选用例/backend/03_Config_JSON扁平化设计.md](../../02_选用例/backend/03_Config_JSON扁平化设计.md) — config 结构
- [02_选用例/backend/09_case_parameter_extractor适配.md](../../02_选用例/backend/09_case_parameter_extractor适配.md) — 参数提取
- [frontend/report/20_TestCaseReportDetail多轮结果.md](../../frontend/report/20_TestCaseReportDetail多轮结果.md) — 前端展示
