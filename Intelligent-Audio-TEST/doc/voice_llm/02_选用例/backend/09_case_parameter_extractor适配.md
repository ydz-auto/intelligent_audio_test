# 09 - case_parameter_extractor 适配（轮次为顶层）

## 涉及文件
- `Intelligent-Audio-TEST/backend/algorithm/case_parameter_extractor.py`

## 现状分析

`CaseParameterExtractor` 从 case_config、device_results、api_results、reference_params 提取评估参数。

## 改造方案

### 参数来源变更

| 参数 | 旧来源 | 新来源 |
|------|--------|--------|
| 音频配置 | `case_config.audios` | `round.audios` |
| 评测维度 | `case_config.dimensions` | `round.evaluation.dimensions` |
| 声纹/干扰人 | `case_config.voiceprintRegistration/interferers` | `round.algorithmParams` 中提取 |
| 参考文本 | `TestCase.reference_params` 列 | 从 `round.referenceParamsPath` 文件读取 |
| 算法参数 | `TestCase.algorithm_params` 列 | `round.algorithmParams` |
| 导轨/音量 | `round.railDistance/volumeLevel` | `round.algorithmParams` 中提取 |
| 等待时间 | `round.waitTime` | `round.algorithmParams` 中提取 |

### algorithmParams 读取辅助函数

```python
def _get_algo_param(algorithm_params, field_code, default=None):
    """从 algorithmParams [{field_code, field_value}] 数组中读取参数"""
    if not algorithm_params:
        return default
    for item in algorithm_params:
        if item.get('field_code') == field_code:
            return item.get('field_value', default)
    return default
```

### 新增参数提取

```python
def get_evaluation_params(self, algorithm_type, round_config, device_results=None,
                           api_results=None, reference_params=None):
    """
    提取评估参数（轮次为顶层版本）
    - round_config: 单轮配置 dict
    - reference_params: 从 referenceParamsPath 文件读取的内容
    """
    params = {}
    algo_params = round_config.get('algorithmParams', [])

    # 1. 从 round_config 结构性字段提取
    params['round_number'] = round_config.get('roundNumber')

    # 2. 从 algorithmParams 提取（[{field_code, field_value}] 数组格式）
    params['input_text'] = _get_algo_param(algo_params, 'inputText', '')
    params['input_audio'] = _get_algo_param(algo_params, 'inputAudio')
    params['wait_time'] = _get_algo_param(algo_params, 'waitTime', 5)

    # 3. E2E 专用（从 algorithmParams 提取）
    params['voiceprint_enabled'] = str(_get_algo_param(algo_params, 'voiceprintEnabled', 'false')).lower() == 'true'

    interferers_raw = _get_algo_param(algo_params, 'interferers')
    if interferers_raw:
        if isinstance(interferers_raw, str):
            interferers = json.loads(interferers_raw)
        else:
            interferers = interferers_raw
        params['interferer_count'] = len(interferers)
    else:
        params['interferer_count'] = 0

    # 4. 参考文本（从文件读取的内容传入）
    if reference_params:
        params['reference_text'] = reference_params.get('reference_text', '')
        params['reference_rttm'] = reference_params.get('reference_rttm', '')

    # 5. 算法参数（本轮，原样传递）
    params['algorithm_params'] = algo_params

    return params
```

### 单轮 vs 整体评估

```python
# 单轮评估
ref = self._load_ref_file(round_config.get('referenceParamsPath'))
params = extractor.get_evaluation_params(
    'voice_llm', round_config, device_results, api_results, ref
)

# 整体评估：聚合所有轮次
all_round_params = []
for round_config in config['rounds']:
    ref = self._load_ref_file(round_config.get('referenceParamsPath'))
    params = extractor.get_evaluation_params(
        'voice_llm', round_config, device_results, api_results, ref
    )
    all_round_params.append(params)
```

## 相关文档
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)
- [03_Config_JSON扁平化设计.md](03_Config_JSON扁平化设计.md)
