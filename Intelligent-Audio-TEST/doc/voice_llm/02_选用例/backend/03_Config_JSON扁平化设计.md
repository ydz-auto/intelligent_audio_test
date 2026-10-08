# 03 - Config JSON 设计（结构性配置 + 独立列参数）

## 涉及文件
- `Intelligent-Audio-TEST/backend/models/models.py:141` (TestCase.config 字段)
- `Intelligent-Audio-TEST/backend/models/models.py` (TestCase.algorithm_params / reference_params 列)

## 改造方案

config 简化为 `{ rounds, dimensions }`，只承载**结构性配置**（音频、维度、轮次编排、环境）。

**算法参数**和**参考参数**从 config 中剥离，回归 `test_cases` 表的独立列：
- `test_cases.algorithm_params`：按轮分组的算法参数（`[{round_number, params:[{field_code, field_value}]}]`）
- `test_cases.reference_params`：按轮分组的参考参数（`[{round_number, reference_params_path, ...}]`）

**设计原则**：
- `config` 只放**结构性配置**（Schema 固定，不随算法变化）：rounds 编排、audios、backgroundNoise、evaluation、dimensions、source_audio、auto_generated
- `test_cases.algorithm_params` 独立列放**算法参数**（由 `case_algorithm_params` 表定义，按轮分组的 `[{round_number, params:[{field_code, field_value}]}]`）
- `test_cases.reference_params` 独立列放**参考参数**（按轮分组的 `[{round_number, reference_params_path, ...}]`，内容仍存文件，列里只存路径等元信息）
- 新增算法参数只需 INSERT case_algorithm_params，无需改代码
- `backgroundNoise` 是 E2E 基础环境配置，放在**round 顶层**（不在 algorithm_params 中）

### 命名约定：前端驼峰 / 后端蛇形

由于 Flask 中间件（`NamingRequest`）会自动将请求体 JSON 的所有 key 转为 snake_case，以及后端 Python 习惯使用蛇形命名，因此：

| 层 | 命名风格 | 示例 |
|----|----------|------|
| **前端（TypeScript / Vue）** | 驼峰（camelCase） | `roundNumber`, `audioId`, `playOrder`, `playbackDeviceId` |
| **后端（Python / 数据库存储）** | 蛇形（snake_case） | `round_number`, `audio_id`, `play_order`, `playback_device_id` |
| **API 响应（后端 → 前端）** | 驼峰（通过 pydantic `by_alias=True` 序列化） | `roundNumber`, `audioId`, `playOrder` |
| **API 请求（前端 → 后端）** | 前端发驼峰，中间件自动转蛇形 | 前端发 `roundNumber`，后端收到 `round_number` |

**存储层（数据库 config 列）使用蛇形 key**，例如：
```json
{
  "rounds": [
    {
      "round_number": 1,
      "audios": [
        { "audio_id": "...", "playback_device_id": "...", "spl": 65, "play_order": 1 }
      ],
      "background_noise": { "audio_id": "...", "device_ids": [], "spl": 55, "loop": true },
      "evaluation": { "enabled": true, "dimensions": [] }
    }
  ]
}
```

**前端兼容两种格式**：`normalizeTestCaseConfig`（`frontend/src/utils/utils.ts`）对每个字段都做了 `camelCase ?? snake_case` 兜底，因此无论后端返回驼峰还是蛇形，前端都能正确解析。

> 下文示例中，config 列的 JSON 统一用**蛇形 key**展示（与实际存储一致）；
> `algorithm_params` / `reference_params` 独立列同样用蛇形 key。

### config 顶层结构（只含结构性配置，蛇形 key）

```json
{
  "rounds": [...],
  "dimensions": [...],
  "background_noise": {...},
  "source_audio": "...",
  "auto_generated": true
}
```

> config 不再包含 `algorithm_params` / `reference_params_path`，这两类参数回归 `test_cases` 表独立列。

### test_cases.algorithm_params 列结构（按轮分组）

```json
[
  {
    "round_number": 1,
    "params": [
      { "field_code": "inputText", "field_value": "今天天气怎么样？" }
    ]
  },
  {
    "round_number": 2,
    "params": [
      { "field_code": "inputText", "field_value": "明天呢？" }
    ]
  }
]
```

### test_cases.reference_params 列结构（按轮分组，只存路径等元信息）

```json
[
  { "round_number": 1, "reference_params_path": "ref_params/93cc5cd7-bd4f-4936-af4c-dae14ab9a098/round_1.json" },
  { "round_number": 2, "reference_params_path": "ref_params/93cc5cd7-bd4f-4936-af4c-dae14ab9a098/round_2.json" }
]
```

> 参考参数内容仍存文件，独立列里只存路径，避免 MB 级数据撑大数据库行。
> 路径格式：`ref_params/{test_case_id}/round_{n}.json`

config 列（蛇形 key，与数据库存储一致）：

```json
{
  "rounds": [
    {
      "round_number": 1,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "id": 1, "name": "WER", "params": {} }
        ]
      }
    },
    {
      "round_number": 2,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "id": 1, "name": "WER", "params": {} }
        ]
      }
    }
  ],
  "dimensions": [
    { "id": 1, "name": "WER", "weight": 1.0, "threshold": 80 }
  ]
}
```

algorithm_params 列：

```json
[
  { "round_number": 1, "params": [
    { "field_code": "inputText", "field_value": "今天天气怎么样？" }
  ]},
  { "round_number": 2, "params": [
    { "field_code": "inputText", "field_value": "明天呢？" }
  ]}
]
```

reference_params 列：

```json
[
  { "round_number": 1, "reference_params_path": "ref_params/93cc5cd7-bd4f-4936-af4c-dae14ab9a098/round_1.json" },
  { "round_number": 2, "reference_params_path": "ref_params/93cc5cd7-bd4f-4936-af4c-dae14ab9a098/round_2.json" }
```

### API 用例示例（多种输入共存）

algorithm_params 列中某一轮：

```json
[
  { "round_number": 1, "params": [
    { "field_code": "inputText", "field_value": "请听这段录音后回答问题" },
    { "field_code": "inputAudio", "field_value": "audio_input_001" }
  ]}
]
```

> **说明**：`inputText` 和 `inputAudio` 同时填写，两种输入共存。
> API 适配器根据 `algorithm_api_params` (direction=input) 构建请求时，
> 两个字段都会包含在请求体中。

### 维度存储：单轮维度 vs 多轮维度

维度分两层存储：

| 层级 | 位置 | 用途 | 结构 |
|------|------|------|------|
| 多轮维度 | `config.dimensions` | 整个用例的评估维度（跨轮聚合/整体评估） | `[{id, name, weight, threshold}]` |
| 单轮维度 | `config.rounds[].evaluation.dimensions` | 仅本轮启用的评估维度（单轮评估） | `[{id, name, params}]` |

- **多轮维度**：用例级配置，所有轮共享的维度集合和权重/阈值，存 `config.dimensions`
- **单轮维度**：轮次级配置，`evaluation.enabled=true` 时必填，控制本轮是否参与评估及本轮的维度参数，存 `config.rounds[].evaluation.dimensions`
- 单轮维度的 `id` 必须在多轮维度集合中存在（引用关系）

### E2E 用例完整示例（test_type='e2e'）

config 列（蛇形 key，与数据库存储一致）：

```json
{
  "rounds": [
    {
      "round_number": 1,
      "audios": [
        { "audio_id": "audio_001", "playback_device_id": "dev_001", "spl": 65, "play_order": 1 }
      ],
      "background_noise": {
        "audio_id": "noise_001", "device_ids": ["dev_002"], "spl": 55, "loop": true
      },
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "id": 2, "name": "SER", "params": {} }
        ]
      }
    },
    {
      "round_number": 2,
      "audios": [
        { "audio_id": "audio_002", "playback_device_id": "dev_001", "spl": 65, "play_order": 1 }
      ],
      "background_noise": {
        "audio_id": "noise_001", "device_ids": ["dev_002"], "spl": 55, "loop": true
      },
      "evaluation": { "enabled": false, "dimensions": [] }
    }
  ],
  "dimensions": [
    { "id": 2, "name": "SER", "weight": 1.0, "threshold": 80 }
  ]
}
```

algorithm_params 列（按轮分组）：

```json
[
  { "round_number": 1, "params": [
    { "field_code": "interferers", "field_value": [{"id":"interferer_1","audioId":"interf_001","playbackDeviceId":"dev_004","spl":60,"startDelay":2,"loop":true}] },
    { "field_code": "railDistance", "field_value": 50 },
    { "field_code": "volumeLevel", "field_value": 70 },
    { "field_code": "voiceprintEnabled", "field_value": true },
    { "field_code": "voiceprintAudioId", "field_value": "vp_audio_001" },
    { "field_code": "voiceprintPlaybackDeviceId", "field_value": "dev_003" },
    { "field_code": "voiceprintSpl", "field_value": 70.0 },
    { "field_code": "voiceprintWaitTime", "field_value": 5.0 },
    { "field_code": "promptAudioId", "field_value": "prompt_001" }
  ]},
  { "round_number": 2, "params": [
    { "field_code": "railDistance", "field_value": 80 },
    { "field_code": "volumeLevel", "field_value": 60 }
  ]}
]
```

reference_params 列（按轮分组）：

```json
[
  { "round_number": 1, "reference_params_path": "ref_params/93cc5cd7-bd4f-4936-af4c-dae14ab9a098/round_1.json" },
  { "round_number": 2, "reference_params_path": "ref_params/93cc5cd7-bd4f-4936-af4c-dae14ab9a098/round_2.json" }
```

### RoundConfigItem 字段定义（结构性配置版）

#### config.rounds[] 结构性字段（Schema 校验，蛇形 key）

| 字段 | 类型 | 必填 | 默认值 | 说明 | 前端驼峰对应 |
|------|------|------|--------|------|-------------|
| round_number | int | 是 | — | 轮次序号 | `roundNumber` |
| audios | list | 否 | [] | 本轮音频列表 | `audios` |
| background_noise | object | 否 | null | 背景噪声配置（E2E 默认有，**轮次顶层**，不在 algorithm_params 中） | `backgroundNoise` |
| evaluation | object | 否 | null | 本轮评估配置（含 enabled + dimensions 单轮维度） | `evaluation` |

> 算法参数和参考参数不在 config.rounds[] 中，分别存 `test_cases.algorithm_params` 和 `test_cases.reference_params` 独立列。
> 前端通过 `normalizeTestCaseConfig` 兼容蛇形和驼峰两种 key。

#### config 顶层结构性字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| rounds | list | 是 | [] | 轮次列表 |
| dimensions | list | 否 | [] | 多轮维度（用例级，跨轮聚合） |
| background_noise | object | 否 | null | 用例级背景噪声（可选，轮级优先） |
| source_audio | string | 否 | null | 源音频文件名 |
| auto_generated | bool | 否 | false | 是否自动生成 |

#### test_cases.algorithm_params 列结构（按轮分组，由 case_algorithm_params 表定义驱动）

`[{round_number, params:[{field_code, field_value}]}]`

| field_code | 类型 | scope | 说明 |
|-----------|------|-------|------|
| `inputText` | string | api | 发送给 API 的文本 |
| `inputAudio` | string | api | 发送给 API 的音频 ID |
| `interferers` | list | common | 干扰人列表 |
| `promptAudioId` | string | common | Prompt 音频 ID |
| `waitTime` | number | common | 等待响应时间(秒) |
| `railDistance` | float | e2e | 导轨距离(cm) |
| `volumeLevel` | float | e2e | 设备音量(0-100) |
| `voiceprintEnabled` | bool | e2e | 声纹注册开关 |
| `voiceprintAudioId` | string | e2e | 声纹注册音频 |
| `voiceprintPlaybackDeviceId` | string | e2e | 声纹播放设备 |
| `voiceprintSpl` | float | e2e | 声纹播放声压级 |
| `voiceprintWaitTime` | float | e2e | 声纹等待时间 |

> 以上 field_code 列表来自 `07_voice_llm算法参数种子数据.md` 中的 INSERT SQL。
> 新增参数只需在数据库中 INSERT，无需修改代码。
> `backgroundNoise` 是 E2E 基础环境配置，放在 round 顶层而非 algorithm_params 中。

#### test_cases.reference_params 列结构（按轮分组，只存路径）

`[{round_number, reference_params_path}]`

> 参考参数内容仍存文件，独立列只存路径，避免 MB 级数据撑大数据库行。

### 保留的数据库列

| 列 | 状态 | 说明 |
|----|------|------|
| `test_cases.algorithm_params` | **保留**（按轮分组） | `[{round_number, params:[{field_code, field_value}]}]` |
| `test_cases.reference_params` | **保留**（按轮分组） | `[{round_number, reference_params_path}]` |
| `test_cases.config` | **保留**（只含结构性配置） | rounds/dimensions/background_noise/source_audio/auto_generated |

### 旧设计 vs 新设计对比

| 方面 | 旧设计 | 新设计 |
|------|--------|--------|
| 算法参数位置 | `config.rounds[].algorithmParams` | `test_cases.algorithm_params` 独立列（按轮分组） |
| 参考参数位置 | `config.rounds[].referenceParamsPath` | `test_cases.reference_params` 独立列（按轮分组，存路径） |
| config 内容 | rounds + dimensions + algorithmParams + referenceParamsPath | 只含结构性配置（rounds/dimensions/background_noise 等） |
| 新增参数 | 改 Schema + 前端代码 | INSERT case_algorithm_params |
| 输入方式 | `inputType` 互斥单选 | `inputText` + `inputAudio` 独立字段，多种共存 |
| referenceParams | 内联 Dict | 独立列，文件路径（按轮分组） |
| backgroundNoise | 在 algorithmParams 中 | round 顶层结构性字段 |
| 单轮维度 | `round.evaluation.dimensions` | `config.rounds[].evaluation.dimensions`（不变） |
| 多轮维度 | `config.dimensions` | `config.dimensions`（不变，用例级跨轮聚合） |
| 命名风格 | 前后端混用驼峰 | **前端驼峰 / 后端蛇形**，中间件自动转换，前端兼容两种 |

## 相关文档
- [01_TestCase模型新增字段.md](01_TestCase模型新增字段.md)
- [04_testcase_Schema新类型.md](04_testcase_Schema新类型.md)
- [07_voice_llm算法参数种子数据.md](../../01_选算法/backend/07_voice_llm算法参数种子数据.md)
- [09_case_parameter_extractor适配.md](09_case_parameter_extractor适配.md)
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)
