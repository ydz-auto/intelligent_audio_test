# 04 - testcase Schema 新类型（参数驱动）

## 涉及文件
- `Intelligent-Audio-TEST/backend/schemas/testcase.py`

## 改造方案

### RoundConfigItem 重构（参数驱动）

> **设计原则**：RoundConfigItem Schema 只保留结构性字段。
> 所有算法相关配置统一存储在 `algorithmParams` 中，
> 由 `case_algorithm_params` 表定义驱动，DynamicForm 在前端动态渲染。
>
> 后端 Schema 不对 algorithmParams 内部的每个 field_code 做类型校验——
> 那是 `case_algorithm_params` 表和前端 DynamicForm 的职责。

```python
class AlgorithmParamItem(Schema):
    """算法参数项 — {field_code, field_value}"""
    field_code = fields.String(required=True)
    field_value = fields.Raw(load_default=None)


class RoundConfigItem(Schema):
    """单轮配置 — 结构性字段 + algorithmParams 兜底"""

    # === 结构性字段（非算法驱动） ===
    roundNumber = fields.Integer(required=True)
    audios = fields.List(fields.Nested(AudioConfigItem), load_default=[])
    backgroundNoise = fields.Nested('BackgroundNoiseConfigSchema', allow_none=True)
    evaluation = fields.Nested('RoundEvaluationConfigItem', allow_none=True)

    # === 算法参数（统一存储，由 case_algorithm_params 定义驱动） ===
    # [{field_code, field_value}] 数组格式
    # 包含输入字段（input_text, input_audio 等）和用例级配置（railDistance, voiceprintEnabled 等）
    algorithmParams = fields.List(fields.Nested(AlgorithmParamItem), load_default=[])

    # === 参考字段（系统自动生成） ===
    referenceParamsPath = fields.String(allow_none=True)

    # === 以下字段全部废弃，移入 algorithmParams ===
    # inputType      → 移除（多种输入共存，由 algorithm_api_params 定义）
    # inputText      → algorithmParams[{field_code:'inputText', field_value:...}]
    # inputAudioId   → algorithmParams[{field_code:'inputAudio', field_value:...}]
    # audioId        → algorithmParams[{field_code:'inputAudio', field_value:...}]
    # waitTime       → algorithmParams[{field_code:'waitTime', field_value:...}]
    # railDistance    → algorithmParams[{field_code:'railDistance', field_value:...}]
    # volumeLevel     → algorithmParams[{field_code:'volumeLevel', field_value:...}]
    # voiceprintRegistration → algorithmParams[{field_code:'voiceprintEnabled', ...}]
    # promptAudioId   → algorithmParams[{field_code:'promptAudioId', field_value:...}]
    # interferers     → algorithmParams[{field_code:'interferers', field_value:...}]
    # interruption    → algorithmParams[{field_code:'interruptionEnabled', ...}]
    # referenceParams → referenceParamsPath（文件路径）
```

### 子 Schema 类（DynamicForm 子编辑器数据结构）

> 以下 Schema 类不再直接用于 RoundConfigItem 的嵌套字段，
> 而是作为 DynamicForm 复杂 param_type 子编辑器的数据结构定义。
> 例如 `param_type=interferer_list` 的编辑器内部使用 `InterfererConfigItem` 做子项校验，
> 值存储在 `algorithmParams` 中 field_code='interferers' 的 field_value 中。

```python
class AudioConfigItem(Schema):
    audio_id = fields.String(required=True)
    playOrder = fields.Integer(load_default=0)
    playbackDeviceId = fields.String(allow_none=True)
    spl = fields.Float(allow_none=True)

class BackgroundNoiseConfigSchema(Schema):
    audioId = fields.String(allow_none=True)
    deviceIds = fields.List(fields.String(), load_default=[])
    spl = fields.Float(load_default=0.0)
    loop = fields.Boolean(load_default=True)

class VoiceprintConfigItem(Schema):
    enabled = fields.Boolean(load_default=False)
    audioId = fields.String(allow_none=True)
    playbackDeviceId = fields.String(allow_none=True)
    spl = fields.Float(load_default=70.0)
    waitTime = fields.Float(load_default=5.0)

class InterfererConfigItem(Schema):
    id = fields.String(required=True)
    audioId = fields.String(required=True)
    playbackDeviceId = fields.String(required=True)
    spl = fields.Float(load_default=60.0)
    startDelay = fields.Float(load_default=0.0)
    loop = fields.Boolean(load_default=True)

class InterruptionConfigItem(Schema):
    enabled = fields.Boolean(load_default=False)
    sensitivity = fields.Float(load_default=0.5, validate=Range(min=0.0, max=1.0))

class RoundEvaluationConfigItem(Schema):
    enabled = fields.Boolean(load_default=False)
    dimensions = fields.List(fields.Nested('DimensionConfigItem'), load_default=[])
```

### TestCaseConfig 简化

```python
class TestCaseConfig(Schema):
    """用例配置 — rounds + dimensions"""
    rounds = fields.List(fields.Nested(RoundConfigItem), load_default=[])
    dimensions = fields.List(fields.Nested('DimensionConfigItem'), load_default=[])
    # 废弃：audios, backgroundNoise, voiceprintRegistration,
    # interferers, roundEvaluation, railDistance, volumeLevel, promptAudioId, interruption
```

### TestCaseSchema 废弃列

```python
class TestCaseSchema(Schema):
    id = fields.String()
    name = fields.String()
    test_type = fields.String()
    related_case_id = fields.String(allow_none=True)
    config = fields.Nested(TestCaseConfig)

    # 废弃列（过渡期保留，新数据不再写入）
    # reference_params → config.rounds[].referenceParamsPath
    # algorithm_params → config.rounds[].algorithmParams
```

### 序列化/反序列化规则

- `algorithmParams` 是 `List[Nested(AlgorithmParamItem)]`，Schema 只校验 `field_code`（String）和 `field_value`（Raw）
- `case_algorithm_params` 表定义才是参数的"类型源"（param_type、default_value 等）
- 后端只保证 algorithmParams 是合法 `[{field_code, field_value}]` 数组，不逐字段校验 field_value 内容

### 数据迁移兼容

```python
def load_legacy_config(config_dict):
    """兼容旧 config 格式 → 新 rounds[] 格式（参数驱动版）"""
    if 'rounds' not in config_dict and 'audios' in config_dict:
        algo_params = []

        for key in ['voiceprintRegistration', 'interferers',
                     'interruption', 'railDistance', 'volumeLevel', 'promptAudioId']:
            val = config_dict.pop(key, None)
            if val is not None:
                algo_params.append({'field_code': key, 'field_value': val})

        legacy_round = {
            'roundNumber': 1,
            'audios': config_dict.pop('audios', []),
            'backgroundNoise': config_dict.pop('backgroundNoise', None),
            'algorithmParams': algo_params,
        }

        dims = config_dict.pop('dimensions', [])
        if dims:
            legacy_round['evaluation'] = {'enabled': True, 'dimensions': dims}

        config_dict['rounds'] = [legacy_round]
        config_dict['dimensions'] = dims

    return config_dict
```

### 旧数据 → 新数据的字段映射

| 旧字段位置 | 新位置 |
|-----------|--------|
| `config.backgroundNoise` | `rounds[0].backgroundNoise`（轮次顶层） |
| `config.railDistance` | `rounds[0].algorithmParams[{field_code:'railDistance', field_value:...}]` |
| `config.volumeLevel` | `rounds[0].algorithmParams[{field_code:'volumeLevel', field_value:...}]` |
| `config.voiceprintRegistration` | `rounds[0].algorithmParams[{field_code:'voiceprintEnabled', ...}]` |
| `config.promptAudioId` | `rounds[0].algorithmParams[{field_code:'promptAudioId', field_value:...}]` |
| `config.interferers` | `rounds[0].algorithmParams[{field_code:'interferers', field_value:...}]` |
| `config.interruption` | `rounds[0].algorithmParams[{field_code:'interruptionEnabled', ...}]` |

## 相关文档
- [03_Config_JSON扁平化设计.md](03_Config_JSON扁平化设计.md)
- [07_voice_llm算法参数种子数据.md](../../01_选算法/backend/07_voice_llm算法参数种子数据.md)
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)
