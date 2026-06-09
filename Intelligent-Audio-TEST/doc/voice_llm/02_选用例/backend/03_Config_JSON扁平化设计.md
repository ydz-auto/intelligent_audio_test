# 03 - Config JSON 设计（参数驱动）

## 涉及文件
- `Intelligent-Audio-TEST/backend/models/models.py:141` (TestCase.config 字段)

## 改造方案

config 简化为 `{ rounds, dimensions }`。每轮包含结构性字段 + `algorithmParams`（统一存储所有算法参数）+ `referenceParamsPath`（参考参数文件路径）。

**设计原则**：
- round 顶层放**结构性字段**（Schema 固定，不随算法变化）
- `algorithmParams` 放**表驱动参数**（由 `case_algorithm_params` 表定义，`[{field_code, field_value}]` 格式）
- 新增参数只需 INSERT case_algorithm_params，无需改代码
- `backgroundNoise` 是 E2E 基础环境配置，放在**round 顶层**（不在 algorithmParams 中）

### config 顶层结构

```json
{
  "rounds": [...],
  "dimensions": [...]
}
```

### API config 示例（test_type='api'）

```json
{
  "rounds": [
    {
      "roundNumber": 1,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 1, "dimension_name": "WER", "params": {} }
        ]
      },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "今天天气怎么样？" }
      ],
      "referenceParamsPath": "/references/round1_ref.json"
    },
    {
      "roundNumber": 2,
      "audios": [],
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 1, "dimension_name": "WER", "params": {} }
        ]
      },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "明天呢？" }
      ],
      "referenceParamsPath": "/references/round2_ref.json"
    }
  ],
  "dimensions": [
    { "dimension_id": 1, "dimension_name": "WER", "params": { "case_sensitive": false } }
  ]
}
```

### API config 示例（多种输入共存）

```json
{
  "rounds": [
    {
      "roundNumber": 1,
      "audios": [],
      "evaluation": { "enabled": true, "dimensions": [...] },
      "algorithmParams": [
        { "field_code": "inputText", "field_value": "请听这段录音后回答问题" },
        { "field_code": "inputAudio", "field_value": "audio_input_001" }
      ],
      "referenceParamsPath": "/references/round1_ref.json"
    }
  ]
}
```

> **说明**：`inputText` 和 `inputAudio` 同时填写，两种输入共存。
> API 适配器根据 `algorithm_api_params` (direction=input) 构建请求时，
> 两个字段都会包含在请求体中。

### E2E config 示例（test_type='e2e'）

```json
{
  "rounds": [
    {
      "roundNumber": 1,
      "audios": [
        { "audio_id": "audio_001", "playbackDeviceId": "dev_001", "spl": 65, "playOrder": 1 }
      ],
      "backgroundNoise": {
        "audioId": "noise_001", "deviceIds": ["dev_002"], "spl": 55, "loop": true
      },
      "evaluation": {
        "enabled": true,
        "dimensions": [
          { "dimension_id": 2, "dimension_name": "SER", "params": {} }
        ]
      },
      "algorithmParams": [
        { "field_code": "interferers", "field_value": "[{\"id\":\"interferer_1\",\"audioId\":\"interf_001\",\"playbackDeviceId\":\"dev_004\",\"spl\":60,\"startDelay\":2,\"loop\":true}]" },
        { "field_code": "railDistance", "field_value": "50" },
        { "field_code": "volumeLevel", "field_value": "70" },
        { "field_code": "voiceprintEnabled", "field_value": "true" },
        { "field_code": "voiceprintAudioId", "field_value": "vp_audio_001" },
        { "field_code": "voiceprintPlaybackDeviceId", "field_value": "dev_003" },
        { "field_code": "voiceprintSpl", "field_value": "70.0" },
        { "field_code": "voiceprintWaitTime", "field_value": "5.0" },
        { "field_code": "promptAudioId", "field_value": "prompt_001" },
        { "field_code": "interruptionEnabled", "field_value": "true" },
        { "field_code": "interruptionSensitivity", "field_value": "0.5" }
      ],
      "referenceParamsPath": "/references/round1_ref.json"
    },
    {
      "roundNumber": 2,
      "audios": [
        { "audio_id": "audio_002", "playbackDeviceId": "dev_001", "spl": 65, "playOrder": 1 }
      ],
      "backgroundNoise": {
        "audioId": "noise_001", "deviceIds": ["dev_002"], "spl": 55, "loop": true
      },
      "evaluation": { "enabled": false },
      "algorithmParams": [
        { "field_code": "railDistance", "field_value": "80" },
        { "field_code": "volumeLevel", "field_value": "60" }
      ],
      "referenceParamsPath": "/references/round2_ref.json"
    }
  ],
  "dimensions": [
    { "dimension_id": 2, "dimension_name": "SER", "params": {} }
  ]
}
```

### RoundConfigItem 字段定义（参数驱动版）

#### 结构性字段（Schema 校验）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| roundNumber | int | 是 | — | 轮次序号 |
| audios | list | 否 | [] | 本轮音频列表 |
| backgroundNoise | object | 否 | null | 背景噪声配置（E2E 默认有，**轮次顶层**，不在 algorithmParams 中） |
| evaluation | object | 否 | null | 本轮评估配置 |
| algorithmParams | list | 否 | [] | 算法参数（`[{field_code, field_value}]`，由 case_algorithm_params 定义驱动） |
| referenceParamsPath | string | 否 | null | 参考参数文件路径 |

#### algorithmParams 内容（由 case_algorithm_params 表定义，不在 Schema 中校验）

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
| `interruptionEnabled` | bool | e2e | 打断检测开关 |
| `interruptionSensitivity` | float | e2e | 打断灵敏度(0~1) |

> 以上 field_code 列表来自 `07_voice_llm算法参数种子数据.md` 中的 INSERT SQL。
> 新增参数只需在数据库中 INSERT，无需修改代码。
> `backgroundNoise` 是 E2E 基础环境配置，放在 round 顶层而非 algorithmParams 中。

### 废弃数据库列

| 列 | 状态 | 替代 |
|----|------|------|
| `reference_params` | **废弃** | `config.rounds[].referenceParamsPath`（文件路径） |
| `algorithm_params` | **废弃** | `config.rounds[].algorithmParams` |

### 旧设计 vs 新设计对比

| 方面 | 旧设计 | 新设计 |
|------|--------|--------|
| 算法字段位置 | 分散到 RoundConfigItem 各字段 | 统一在 `algorithmParams[{field_code, field_value}]` |
| 新增参数 | 改 Schema + 前端代码 | INSERT case_algorithm_params |
| 输入方式 | `inputType` 互斥单选 | `inputText` + `inputAudio` 独立字段，多种共存 |
| referenceParams | 内联 Dict (`referenceParams`) | 文件路径 (`referenceParamsPath`) |
| backgroundNoise | 在 algorithmParams 中 | round 顶层结构性字段 |
| waitTime | 轮次顶层 | algorithmParams 中（field_code=waitTime） |

## 相关文档
- [01_TestCase模型新增字段.md](01_TestCase模型新增字段.md)
- [04_testcase_Schema新类型.md](04_testcase_Schema新类型.md)
- [07_voice_llm算法参数种子数据.md](../../01_选算法/backend/07_voice_llm算法参数种子数据.md)
- [10_reference_params_generator适配.md](10_reference_params_generator适配.md)
