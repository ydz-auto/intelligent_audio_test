# 01_types.ts 新接口定义

> 文件：`frontend/src/components/common/test-case/TestCaseModal/types.ts`

## 现状分析

当前 `types.ts` 定义了用例编辑模态窗的类型系统：

```ts
interface AudioConfig {
  audioId: string
  testType: 'api' | 'e2e'     // 已废弃
  playbackDeviceId: string
  spl: number
  playOrder: number
}

interface TestCaseFormData {
  config: {
    audios: AudioConfig[]
    dimensions: { api: DimensionConfig[], e2e: DimensionConfig[] }
    backgroundNoise: BackgroundNoiseConfig
  }
}
```

## 改造方案（轮次为顶层）

config 简化为 `{ rounds, dimensions }`，每一轮完全自包含。

### 1. AudioConfig 移除 testType

```ts
interface AudioConfig {
  audioId: string
  playbackDeviceId: string   // E2E 专用
  spl: number                // E2E 专用
  playOrder: number
}
```

### 2. BackgroundNoiseConfig 新增 loop

```ts
interface BackgroundNoiseConfig {
  audioId: string
  deviceIds: string[]
  spl: number
  loop: boolean   // true=循环播放（默认），false=播完自然结束
}
```

### 3. RoundConfigItem — 轮次配置（核心接口，参数驱动）

> **设计原则：参数驱动，不硬编码**
>
> RoundConfigItem 只保留结构性字段。所有算法相关配置统一存储在 `algorithmParams` 中，
> 由 `case_algorithm_params` 表定义驱动，DynamicForm 动态渲染。
>
> **输入方式**：不再使用互斥单选 `inputType`。
> 单轮支持多种输入共存——由 `algorithm_api_params` (direction=input) 定义决定，
> 输入值同样存储在 `algorithmParams` 中（field_code = param_code）。

```ts
interface AlgorithmParamItem {
  field_code: string
  field_value: any
}

interface RoundConfigItem {
  // === 结构性字段（非算法驱动） ===
  roundNumber: number                  // 轮次序号（前端自动编号）
  audios?: AudioConfig[]               // 本轮音频列表
  backgroundNoise?: BackgroundNoiseConfig  // E2E 基础环境配置（轮次顶层）
  evaluation?: RoundEvaluationConfig   // 本轮评估配置

  // === 算法参数（统一存储，由 case_algorithm_params 定义驱动） ===
  // [{field_code, field_value}] 数组格式
  // 包含：
  //   - 输入字段（来自 algorithm_api_params direction=input）
  //     例: {field_code:'inputText', field_value:'今天天气怎么样'}
  //         {field_code:'inputAudio', field_value:'audio_001'}（多种输入共存）
  //   - 用例级配置（来自 case_algorithm_params）
  //     例: {field_code:'railDistance', field_value:'50'}
  //         {field_code:'voiceprintEnabled', field_value:'true'}
  //         {field_code:'interferers', field_value:'[...]'}
  algorithmParams: AlgorithmParamItem[]

  // === 参考字段（系统自动生成，只读） ===
  referenceParamsPath?: string         // 参考参数文件路径

  // === 废弃字段，全部移入 algorithmParams ===
  // inputType      → 移除（多种输入共存，由 algorithm_api_params 定义）
  // inputText      → {field_code:'inputText', field_value:...}
  // inputAudioId   → {field_code:'inputAudio', field_value:...}
  // audioId        → {field_code:'inputAudio', field_value:...}
  // waitTime       → {field_code:'waitTime', field_value:...}
  // railDistance    → {field_code:'railDistance', field_value:...}
  // volumeLevel     → {field_code:'volumeLevel', field_value:...}
  // voiceprintRegistration → {field_code:'voiceprintEnabled', ...}
  // promptAudioId   → {field_code:'promptAudioId', field_value:...}
  // interferers     → {field_code:'interferers', field_value:...}
  // referenceParams → referenceParamsPath（文件路径）
}
```

### 4. 子配置接口（DynamicForm 子编辑器的数据结构）

> 以下接口不再直接作为 RoundConfigItem 的子字段，而是作为 DynamicForm 复杂 param_type
> 的子编辑器数据结构。例如 `param_type=interferer_list` 的编辑器内部使用 `InterfererConfigItem`，
> 值存储在 `algorithmParams` 中 field_code='interferers' 的 field_value 中。

```ts
interface VoiceprintConfig {
  enabled: boolean
  audioId?: string
  playbackDeviceId?: string
  spl?: number
  waitTime?: number
}

interface InterfererConfigItem {
  id: string
  audioId: string
  playbackDeviceId: string
  spl: number
  startDelay: number
  loop: boolean
}

interface RoundEvaluationConfig {
  enabled: boolean
  dimensions: DimensionConfig[]
}

interface InterruptionConfig {
  enabled: boolean
  sensitivity: number
}
```

### 5. TestCaseConfig — config 为 rounds + dimensions

```ts
interface TestCaseConfig {
  rounds: RoundConfigItem[]
  dimensions: DimensionConfig[]
  // 废弃：audios, backgroundNoise, voiceprintRegistration,
  // interferers, roundEvaluation, railDistance, volumeLevel, promptAudioId, interruption
}
```

### 6. TestCaseFormData

```ts
interface TestCaseFormData {
  name: string
  description?: string
  group?: string
  groupId?: number
  tags?: string[]
  algorithmType?: string
  test_type: 'api' | 'e2e'
  config: TestCaseConfig
}
```

### 7. TestCase 接口

```ts
interface TestCase {
  test_type: 'api' | 'e2e'
  config: TestCaseConfig
  // 废弃列：reference_params → 文件+rounds[].referenceParamsPath
  // 废弃列：algorithm_params → rounds[].algorithmParams
}
```

## 废弃字段汇总

### config 顶层废弃

| 字段 | 原位置 | 新位置 |
|------|--------|--------|
| `config.audios` | config 顶层 | `rounds[].audios` |
| `config.dimensions` | config 顶层 | `rounds[].evaluation.dimensions` |
| `config.roundEvaluation` | config 顶层 | `rounds[].evaluation` |
| `reference_params` | TestCase 列 | `rounds[].referenceParamsPath`（文件路径） |
| `algorithm_params` | TestCase 列 | `rounds[].algorithmParams` |

### RoundConfigItem 废弃字段（参数驱动改造）

> 以下字段从 RoundConfigItem 接口移除，统一由 `case_algorithm_params` 表定义驱动，
> 值存储在 `rounds[].algorithmParams` 中（`{field_code, field_value}` 格式）。

| 字段 | 原位置 | 新位置 | 对应 field_code |
|------|--------|--------|----------------|
| `inputType` | RoundConfigItem | **移除**（多种输入共存） | — |
| `inputText` | RoundConfigItem | algorithmParams | `inputText` |
| `inputAudioId` | RoundConfigItem | algorithmParams | `inputAudio` |
| `audioId` | RoundConfigItem | algorithmParams | `inputAudio` |
| `waitTime` | RoundConfigItem | algorithmParams | `waitTime` |
| `railDistance` | RoundConfigItem | algorithmParams | `railDistance` |
| `volumeLevel` | RoundConfigItem | algorithmParams | `volumeLevel` |
| `voiceprintRegistration` | RoundConfigItem | algorithmParams | `voiceprintEnabled` + `voiceprintAudioId` + ... |
| `promptAudioId` | RoundConfigItem | algorithmParams | `promptAudioId` |
| `interferers` | RoundConfigItem | algorithmParams | `interferers` |
| `referenceParams` | RoundConfigItem | referenceParamsPath | — |

## 不变部分

- `TestCaseGroup`、`TestCaseGroupItem` — 不变
- `PlaybackDevice`、`ImportPreviewItem` — 不变
- `AssociatedDimension`、`AlgorithmOption` — 不变
- `DimensionConfig` — 不变（在每轮 evaluation.dimensions 中使用）

## 引用关系

- ← `02_选用例/backend/03_Config_JSON扁平化设计`
- ← `02_选用例/backend/04_testcase_Schema新类型`
- → `02_选用例/frontend/02_businessTypes适配`
- → `02_选用例/frontend/06_CaseForm_test_type驱动`
- → `02_选用例/frontend/10_RoundConfigEditor`
- → `02_选用例/frontend/12_VoiceprintConfigEditor`
- → `02_选用例/frontend/13_InterfererConfigEditor`
- → `02_选用例/frontend/14_RoundEvaluationEditor`
