# 09 - case_parameter_extractor 适配（轮次为顶层）

## 涉及文件
- `Intelligent-Audio-TEST/backend/utils/algorithm/case_parameter_extractor.py`

## 现状分析

`CaseParameterExtractor` 从 case_config、device_results、api_results、reference_params 提取评估参数。

## 改造方案

### 参数来源变更

| 参数 | 旧来源 | 新来源 |
|------|--------|--------|
| 音频配置 | `case_config.audios` | `round.audios` |
| 评测维度（单轮） | `case_config.dimensions` | `round.evaluation.dimensions` |
| 评测维度（多轮） | `case_config.dimensions` | `config.dimensions` |
| 声纹/干扰人 | `case_config.voiceprintRegistration/interferers` | `TestCase.algorithm_params` 列中按 `round_number` 取本轮 `params`，再提取 |
| 参考文本 | `TestCase.reference_params` 列 | `TestCase.reference_params` 列中按 `round_number` 取本轮 `reference_params_path`，从文件读取 |
| 算法参数 | `TestCase.algorithm_params` 列 | `TestCase.algorithm_params` 列（按轮分组 `[{round_number, params}]`） |
| 导轨/音量 | `round.railDistance/volumeLevel` | `TestCase.algorithm_params` 列本轮 params 中提取 |
| 等待时间 | `round.waitTime` | `TestCase.algorithm_params` 列本轮 params 中提取 |

### algorithm_params 列读取辅助函数

```python
def _get_round_algo_params(algorithm_params_col: list, round_number: int) -> list:
    """从 test_cases.algorithm_params 列（按轮分组）中读取指定轮的 params

    Args:
        algorithm_params_col: [{round_number, params:[{field_code, field_value}]}]
        round_number: 轮次序号
    Returns:
        该轮的 params 列表 [{field_code, field_value}]，找不到返回 []
    """
    if not algorithm_params_col:
        return []
    for item in algorithm_params_col:
        if item.get('round_number') == round_number:
            return item.get('params', [])
    return []


def _get_algo_param(algo_params: list, field_code: str, default=None):
    """从 params [{field_code, field_value}] 数组中读取参数值"""
    if not algo_params:
        return default
    for item in algo_params:
        if item.get('field_code') == field_code:
            return item.get('field_value', default)
    return default
```

### 新增参数提取

```python
def get_evaluation_params(self, algorithm_type, round_config, algorithm_params_col,
                           reference_params_col, device_results=None,
                           api_results=None):
    """
    提取评估参数（轮次为顶层版本）
    - round_config: 单轮配置 dict（来自 config.rounds[]，只含结构性字段）
    - algorithm_params_col: test_cases.algorithm_params 列（按轮分组）
    - reference_params_col: test_cases.reference_params 列（按轮分组）
    """
    params = {}
    round_number = round_config.get('roundNumber')
    algo_params = _get_round_algo_params(algorithm_params_col, round_number)

    # 1. 从 round_config 结构性字段提取
    params['round_number'] = round_number

    # 2. 从 algorithm_params 列本轮 params 提取（[{field_code, field_value}] 数组格式）
    params['input_text'] = _get_algo_param(algo_params, 'inputText', '')
    params['input_audio'] = _get_algo_param(algo_params, 'inputAudio')
    params['wait_time'] = _get_algo_param(algo_params, 'waitTime', 5)

    # 3. E2E 专用
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

    # 4. 参考文本（从 reference_params 列取路径，再读文件）
    ref = self._load_round_ref_file(reference_params_col, round_number)
    if ref:
        params['reference_text'] = ref.get('reference_text', '')
        params['reference_rttm'] = ref.get('reference_rttm', '')

    # 5. 算法参数（本轮，原样传递）
    params['algorithm_params'] = algo_params

    return params
```

### 单轮 vs 整体评估

```python
# 单轮评估
params = extractor.get_evaluation_params(
    'voice_llm', round_config, algorithm_params_col, reference_params_col,
    device_results, api_results
)

# 整体评估：聚合所有轮次
all_round_params = []
for round_config in config['rounds']:
    params = extractor.get_evaluation_params(
        'voice_llm', round_config, algorithm_params_col, reference_params_col,
        device_results, api_results
    )
    all_round_params.append(params)
```

## 相关文档
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)
- [03_Config_JSON扁平化设计.md](03_Config_JSON扁平化设计.md)
