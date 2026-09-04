# 04 - testcase Schema 新类型（结构性配置 + 独立列参数）

## 涉及文件
- `Intelligent-Audio-TEST/backend/schemas/testcase.py`（Pydantic 定义；基类 `APIModel` 见 `backend/schemas/base.py:5-12`：`alias_generator=to_camel` + `populate_by_name` + `serialize_by_alias`，字段统一蛇形命名、对外支持 camelCase 别名）
- 关联：
  - `Intelligent-Audio-TEST/backend/controllers/testcase_controller.py`（创建/更新时剥离 config 中的算法参数并写入独立列、读取时兼容旧数据格式）
  - `Intelligent-Audio-TEST/backend/utils/algorithm/reference_params_generator.py`（生成参考参数文件并把路径写入 reference_params 独立列）

## 现状分析

> 本文档原为改造设计稿；实际代码已落地并演进为 **Pydantic v2（APIModel）** 定义，并非设计稿中的 marshmallow `Schema`（无 `fields.Integer`/`load_default`/`Schema` 字符串嵌套等写法）。
> 以下内容已与实际代码对齐，实际未实现的类均明确标注。

### RoundConfigItem（只含结构性字段）— 已落地

> 设计原则不变：RoundConfigItem Schema 只保留结构性字段。
> 算法参数和参考参数不在 config.rounds[] 中，分别存 `test_cases.algorithm_params` 和 `test_cases.reference_params` 独立列（按轮分组）。
> 算法参数由 `case_algorithm_params` 表定义驱动，DynamicForm 在前端动态渲染。

实际代码（schemas/testcase.py:66-79）：

```python
class RoundConfigItem(APIModel):
    """单轮配置项 — 只含结构性字段

    算法参数和参考参数不在 config.rounds[] 中：
      - algorithm_params → test_cases.algorithm_params 独立列（按轮分组 [{round_number, params}]）
      - reference_params → test_cases.reference_params 独立列（按轮分组 [{round_number, reference_params_path}]）
    """
    model_config = ConfigDict(extra='allow')

    # === 结构性字段 ===
    round_number: Optional[int] = Field(1, alias='round_number', validation_alias=AliasChoices('round_number', 'roundNumber'))
    audios: Optional[List[TestCaseAudioConfigItem]] = Field(default_factory=list, alias='audios', validation_alias='audios')
    background_noise: Optional[TestCaseBackgroundNoiseItem] = Field(None, alias='background_noise', validation_alias=AliasChoices('background_noise', 'backgroundNoise'))
    evaluation: Optional[Dict[str, Any]] = Field(None, alias='evaluation', validation_alias='evaluation')
```

与设计稿的差异：
- 框架：marshmallow → Pydantic（`APIModel`），字段为 `Optional[...]` + `Field(默认值, alias=..., validation_alias=AliasChoices(...))`；字段名蛇形（`round_number`/`background_noise`），兼容 camelCase 入参（`roundNumber`/`backgroundNoise`）。
- `audios` 元素类型为 `TestCaseAudioConfigItem`（非设计稿的 `AudioConfigItem`）；`background_noise` 嵌套类型为 `TestCaseBackgroundNoiseItem`（非 `BackgroundNoiseConfigSchema`）。
- `evaluation` 为 `Optional[Dict[str, Any]]` 透传字典——**实际未实现**设计稿中的 `RoundEvaluationConfigItem` 子 Schema。
- `model_config = ConfigDict(extra='allow')`：透传轮内未知字段（如历史遗留字段），宽松校验。

### AlgorithmParamItem 与参考参数 Schema

实际代码（schemas/testcase.py:325-360 与 363-390）：

```python
class AlgorithmParamItem(APIModel):
    """算法参数项 — {field_code, field_value}

    field_value 类型由 case_algorithm_params 表的 param_type 定义决定，
    Schema 层不限制具体类型，支持 str/int/float/bool/list/dict 等。
    """
    model_config = ConfigDict(extra='allow')

    field_code: Optional[str] = Field(None, alias='field_code', validation_alias=AliasChoices('field_code', 'fieldCode'))
    field_value: Optional[Any] = Field(None, alias='field_value', validation_alias=AliasChoices('field_value', 'fieldValue'))

    @staticmethod
    def convert_params(params) -> Optional[List['AlgorithmParamItem']]:  # 支持 list[dict] / list[item] / dict{code:value}

class ReferenceParamItem(APIModel):
    model_config = ConfigDict(extra='allow')

    code: Optional[str] = ...            # 363
    type: Optional[str] = ...            # 364
    value: Optional[Union[str, Dict[str, Any], List[Any]]] = ...  # 365
    annotation_code: Optional[str] = ... # 366
    annotation_format: Optional[str] = ...  # 367

    @staticmethod
    def convert_params(params) -> Optional[List['ReferenceParamItem']]: ...
```

与设计稿的差异：
- **实际未实现**：设计稿中的 `RoundAlgorithmParams`、`RoundReferenceParams` 两个类不存在。
- `test_cases.reference_params` 独立列的元素结构实际由 `reference_params_generator.py:395-398` 写入的 `{round_number, reference_params_path}` 决定（路径指向该轮独立生成的 JSON 文件），并非由 Schema 类约束。
- `ReferenceParamItem`（code/type/value/annotation_code/annotation_format）用于参考参数文件内单条参数的结构，目前仅被自身 `convert_params` 引用（仅定义、无外部强依赖）。

### 子 Schema 类（实际命名与字段）

> 这些类不再用于 config 数据结构（见上），而是作为 config/独立列中嵌套子项的结构定义。

| 设计稿类名 | 实际类名（行号） | 实际字段 | 说明 |
|-----------|-----------------|---------|------|
| `AudioConfigItem` | `TestCaseAudioConfigItem`（14-38） | `id`、`audio_id`、`audio_name`、`spl`、`playback_device_id`、`playback_device_name`、`play_order`、`background_noise`（轮次级）、`interferers`（segment 级） | `extra='allow'` 保留前端传入的额外字段；`spl` 空串转 `None` |
| `BackgroundNoiseConfigSchema` | `TestCaseBackgroundNoiseItem`（41-55） | `audio_id`、`audio`、`audio_name`、`spl`、`device_ids`、`playback_device_names`、`playback_device_name`、`device_names`、`loop`（默认 True） | `extra='allow'` 保留文件名/设备名数组等 |
| `VoiceprintConfigItem` | **未实现** | — | 代码中无对应类 |
| `InterfererConfigItem` | **未实现** | — | 干扰人在 `TestCaseAudioConfigItem` 中为 `Optional[List[Dict[str, Any]]]`（28 行），值存于 `algorithm_params` 独立列对应轮的 `field_code='interferers'` |
| `RoundEvaluationConfigItem` | **未实现** | — | `evaluation` 为 `Optional[Dict[str, Any]]` |
| `DimensionConfigItem` | `TestCaseDimensionItem`（58-63） | `id`、`name`、`weight`、`threshold`、`test_type`（维度按测试类型区分，元素带 `test_type` 字段） | 维度为扁平列表，不再使用 `dimensions = {api:[], e2e:[]}` 嵌套 |

### TestCaseConfig（只含结构性配置）— 已落地

实际代码（schemas/testcase.py:82-92）：

```python
class TestCaseConfig(APIModel):
    """测试用例配置 — 只含结构性配置
    config = { rounds, dimensions, background_noise, source_audio, auto_generated }
    算法参数和参考参数在独立列，不在 config 中
    """
    model_config = ConfigDict(extra='allow')
    rounds: Optional[List[RoundConfigItem]] = Field(default_factory=list, alias='rounds', validation_alias='rounds')
    dimensions: Optional[List[TestCaseDimensionItem]] = Field(default_factory=list, alias='dimensions', validation_alias='dimensions')
    background_noise: Optional[Dict[str, Any]] = Field(None, alias='background_noise', validation_alias=AliasChoices('background_noise', 'backgroundNoise'))
    source_audio: Optional[str] = Field(None, alias='source_audio', validation_alias=AliasChoices('source_audio', 'sourceAudio'))
    auto_generated: Optional[bool] = Field(False, alias='auto_generated', validation_alias=AliasChoices('auto_generated', 'autoGenerated'))
```

与设计稿差异：`background_noise` 为 `Optional[Dict[str, Any]]`（用例级透传字典，非嵌套子 Schema）；`dimensions` 元素为 `TestCaseDimensionItem`。

### 用例出参模型（实际非 TestCaseSchema）

- **实际未实现**设计稿中的 `TestCaseSchema` 类。
- 列表/详情出参模型为 `TestCaseListItem`（schemas/testcase.py:95-109）与 `TestCaseDetailData`（122-139），字段：`id`、`name`、`description`、`group_id`、`group_name`、`type`、`tags`、`config: TestCaseConfig`、`algorithm_params: Optional[Any]`、`reference_params: Optional[Any]`、`algorithm_type`、`created_at`、`updated_at`、`total_duration`（详情另有 `group`/`audios`/`dimensions`）。
- 注意：出参模型**没有 `test_type` 字段**；`type` 字段由 controller 填充为 `tc.test_type or 'api'`（testcase_controller.py:407 / 531 / 624）。
- `algorithm_params` / `reference_params` 为 `Optional[Any]`（宽松透传 JSON 列，不强制嵌套列表结构），而非设计稿的 `List[Nested(...)]`。

### 序列化/反序列化规则

- 请求侧 `TestCaseCreateSchema`（393-456）与 `TestCaseUpdateSchema`（520-576）均含：
  - `coerce_dict_to_list`（validator）：`algorithm_params` 为 dict 时转换为平面 `[{field_code, field_value}]`（向后兼容旧格式）。
  - `get_algorithm_params_dict()`：新格式（首个元素含 `round_number` 或 `params` 键）原样返回；旧平面格式 `[{field_code, field_value}]` 包装为 `round_number=1` 的单轮输出（`[{round_number:1, params:[...]}]`）。
  - `get_reference_params_dict()`：list 原样返回。
- controller 创建/更新时剥离 `config.rounds[]` 中的 `algorithmParams`/`algorithm_params`/`referenceParamsPath`/`reference_params_path`（testcase_controller.py:683-688、855-871），算法参数写入 `test_cases.algorithm_params` 列（744-750，兼容平面格式包装为单轮）。
- `test_cases.algorithm_params` 列是"按轮分组"结构 `[{round_number, params:[{field_code, field_value}]}]`；读取侧按轮取用（`testcase_controller.py:126-144 _get_algo_params_list_from_columns`）。
- `test_cases.reference_params` 列结构为 `[{round_number, reference_params_path}]`，由 reference_params_generator 写入（见下节）。
- `case_algorithm_params` 表定义才是参数的"类型源"（param_type、default_value 等）。
- 后端只保证 algorithm_params 列中每轮的 params 是合法 `[{field_code, field_value}]` 数组，不逐字段校验 field_value 内容。

### 数据迁移兼容（实际实现）

- **实际未实现**设计稿中的 `load_legacy_config` 函数。
- 实际兼容策略分三层：
  1. **Schema 层**：`coerce_dict_to_list` 完成 dict→平面 list 转换；`get_algorithm_params_dict` 将旧平面格式包装为 `round_number=1` 单轮（见上）。
  2. **Controller 读取层**：`_extract_algorithm_params`（testcase_controller.py:109-124）兼容旧数据 `config.rounds[0].algorithmParams` 为 dict 的情况，统一转 `[{field_code, field_value}]` 列表后再交给执行侧。
  3. **reference_params_generator**（reference_params_generator.py:337-411 `apply_to_config`）：从 config 仅读取轮次列表（config 已不含 `reference_params_path`），逐轮生成参考参数文件，路径写入 `test_case.reference_params` 独立列（395-398），不再回写 config。

### 旧数据 → 新数据的字段映射

| 旧字段位置 | 新位置 |
|-----------|--------|
| `config.rounds[].algorithmParams` | `test_cases.algorithm_params` 列（按轮分组 `[{round_number, params:[{field_code, field_value}]}]`） |
| `config.rounds[].referenceParamsPath` | `test_cases.reference_params` 列（按轮分组 `[{round_number, reference_params_path}]`） |
| `config.backgroundNoise` | `config.background_noise`（用例级，TestCaseConfig）或 `config.rounds[].background_noise`（轮次级，RoundConfigItem；字段兼容 camelCase 别名 `backgroundNoise`） |

## 相关文档
- [03_Config_JSON扁平化设计.md](03_Config_JSON扁平化设计.md)
- [07_voice_llm算法参数种子数据.md](../../01_选算法/backend/07_voice_llm算法参数种子数据.md)
- [09_case_parameter_extractor适配.md](09_case_parameter_extractor适配.md)
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)