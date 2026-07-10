# 04 - testcase Schema 新类型（结构性配置 + 独立列参数）

## 涉及文件
- `Intelligent-Audio-TEST/backend/schemas/testcase.py`

## 改造方案

### RoundConfigItem 重构（只含结构性字段）

> **设计原则**：RoundConfigItem Schema 只保留结构性字段。
> 算法参数和参考参数不在 config.rounds[] 中，分别存 `test_cases.algorithm_params` 和 `test_cases.reference_params` 独立列（按轮分组）。
> 算法参数由 `case_algorithm_params` 表定义驱动，DynamicForm 在前端动态渲染。

```python
class RoundConfigItem(Schema):
    """单轮配置 — 只含结构性字段"""

    # === 结构性字段（非算法驱动） ===
    roundNumber = fields.Integer(required=True)
    audios = fields.List(fields.Nested(AudioConfigItem), load_default=[])
    backgroundNoise = fields.Nested('BackgroundNoiseConfigSchema', allow_none=True)
    evaluation = fields.Nested('RoundEvaluationConfigItem', allow_none=True)

    # 算法参数和参考参数不在 config.rounds[] 中：
    # - algorithm_params → test_cases.algorithm_params 独立列（按轮分组 [{round_number, params}]）
    # - reference_params → test_cases.reference_params 独立列（按轮分组 [{round_number, reference_params_path}]）
```

### AlgorithmParamItem（用于独立列的 params 元素）

```python
class AlgorithmParamItem(Schema):
    """算法参数项 — {field_code, field_value}"""
    field_code = fields.String(required=True)
    field_value = fields.Raw(load_default=None)


class RoundAlgorithmParams(Schema):
    """按轮分组的算法参数项 — test_cases.algorithm_params 列的元素"""
    round_number = fields.Integer(required=True)
    params = fields.List(fields.Nested(AlgorithmParamItem), load_default=[])


class RoundReferenceParams(Schema):
    """按轮分组的参考参数项 — test_cases.reference_params 列的元素"""
    round_number = fields.Integer(required=True)
    reference_params_path = fields.String(allow_none=True)
```

### 子 Schema 类（DynamicForm 子编辑器数据结构）

> 以下 Schema 类不再直接用于 RoundConfigItem 的嵌套字段，
> 而是作为 DynamicForm 复杂 param_type 子编辑器的数据结构定义。
> 例如 `param_type=interferer_list` 的编辑器内部使用 `InterfererConfigItem` 做子项校验，
> 值存储在 `test_cases.algorithm_params` 列对应轮的 params 中 field_code='interferers' 的 field_value 中。

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

class RoundEvaluationConfigItem(Schema):
    enabled = fields.Boolean(load_default=False)
    dimensions = fields.List(fields.Nested('DimensionConfigItem'), load_default=[])
```

### TestCaseConfig 简化（只含结构性配置）

```python
class TestCaseConfig(Schema):
    """用例配置 — 只含结构性配置
    算法参数和参考参数在独立列，不在 config 中
    """
    rounds = fields.List(fields.Nested(RoundConfigItem), load_default=[])
    dimensions = fields.List(fields.Nested('DimensionConfigItem'), load_default=[])  # 多轮维度
    background_noise = fields.Nested('BackgroundNoiseConfigSchema', allow_none=True)  # 用例级
    source_audio = fields.String(allow_none=True)
    auto_generated = fields.Boolean(load_default=False)
```

### TestCaseSchema（保留独立列）

```python
class TestCaseSchema(Schema):
    id = fields.String()
    name = fields.String()
    test_type = fields.String()
    config = fields.Nested(TestCaseConfig)  # 只含结构性配置

    # 独立列（保留，按轮分组）
    algorithm_params = fields.List(fields.Nested(RoundAlgorithmParams), load_default=[])
    reference_params = fields.List(fields.Nested(RoundReferenceParams), load_default=[])
```

### 序列化/反序列化规则

- `test_cases.algorithm_params` 列是 `List[Nested(RoundAlgorithmParams)]`，每项含 `round_number` + `params: [{field_code, field_value}]`
- `test_cases.reference_params` 列是 `List[Nested(RoundReferenceParams)]`，每项含 `round_number` + `reference_params_path`
- `case_algorithm_params` 表定义才是参数的"类型源"（param_type、default_value 等）
- 后端只保证 algorithm_params 列中每轮的 params 是合法 `[{field_code, field_value}]` 数组，不逐字段校验 field_value 内容

### 数据迁移兼容

```python
def load_legacy_config(config_dict, algorithm_params_col=None, reference_params_col=None):
    """兼容旧 config 格式 → 新结构（结构性 config + 独立列参数）

    旧 config 中 rounds[].algorithmParams / referenceParamsPath
    需迁移到 test_cases.algorithm_params / reference_params 独立列（按轮分组）
    """
    algo_rounds = []
    ref_rounds = []

    for round_item in config_dict.get('rounds', []):
        round_number = round_item.get('roundNumber', 1)

        # 提取旧 algorithmParams → 独立列
        old_algo = round_item.pop('algorithmParams', None)
        if old_algo is not None:
            algo_rounds.append({
                'round_number': round_number,
                'params': old_algo
            })

        # 提取旧 referenceParamsPath → 独立列
        old_ref_path = round_item.pop('referenceParamsPath', None)
        if old_ref_path is not None:
            ref_rounds.append({
                'round_number': round_number,
                'reference_params_path': old_ref_path
            })

    return config_dict, algo_rounds, ref_rounds
```

### 旧数据 → 新数据的字段映射

| 旧字段位置 | 新位置 |
|-----------|--------|
| `config.rounds[].algorithmParams` | `test_cases.algorithm_params` 列（按轮分组） |
| `config.rounds[].referenceParamsPath` | `test_cases.reference_params` 列（按轮分组） |
| `config.backgroundNoise` | `config.rounds[0].backgroundNoise`（轮次顶层）或 `config.background_noise`（用例级） |

## 相关文档
- [03_Config_JSON扁平化设计.md](03_Config_JSON扁平化设计.md)
- [07_voice_llm算法参数种子数据.md](../../01_选算法/backend/07_voice_llm算法参数种子数据.md)
- [09_case_parameter_extractor适配.md](09_case_parameter_extractor适配.md)
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)
