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

## 改造方案（结构性配置 + 独立列参数）

config 只承载结构性配置（rounds/dimensions 等）。算法参数和参考参数回归 `test_cases` 表独立列（按轮分组）。

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

### 3. RoundConfigItem — 轮次配置（核心接口，只含结构性字段）

> **设计原则：结构性配置与参数分离**
>
> RoundConfigItem 只保留结构性字段。算法参数和参考参数不在 config.rounds[] 中，
> 分别存 `test_cases.algorithm_params` 和 `test_cases.reference_params` 独立列（按轮分组）。
> 算法参数由 `case_algorithm_params` 表定义驱动，DynamicForm 动态渲染。

```ts
interface AlgorithmParamItem {
  field_code: string
  field_value: any
}

interface RoundAlgorithmParams {
  // test_cases.algorithm_params 列的元素（按轮分组）
  round_number: number
  params: AlgorithmParamItem[]
}

interface RoundReferenceParams {
  // test_cases.reference_params 列的元素（按轮分组）
  round_number: number
  reference_params_path: string
}

interface RoundConfigItem {
  // === 结构性字段（非算法驱动） ===
  roundNumber: number                  // 轮次序号（前端自动编号）
  audios?: AudioConfig[]               // 本轮音频列表
  backgroundNoise?: BackgroundNoiseConfig  // E2E 基础环境配置（轮次顶层）
  evaluation?: RoundEvaluationConfig   // 本轮评估配置

  // 算法参数和参考参数不在 config.rounds[] 中：
  // - algorithm_params → test_cases.algorithm_params 独立列（按轮分组 [{round_number, params}]）
  // - reference_params → test_cases.reference_params 独立列（按轮分组 [{round_number, reference_params_path}]）
}
```

### 4. 子配置接口（DynamicForm 子编辑器的数据结构）

> 以下接口不再直接作为 RoundConfigItem 的子字段，而是作为 DynamicForm 复杂 param_type
> 的子编辑器数据结构。例如 `param_type=interferer_list` 的编辑器内部使用 `InterfererConfigItem`，
> 值存储在 `test_cases.algorithm_params` 列对应轮的 params 中 field_code='interferers' 的 field_value 中。

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
  dimensions: DimensionConfig[]  // 单轮维度
}

interface InterruptionConfig {
  enabled: boolean
  sensitivity: number
}
```

### 5. TestCaseConfig — config 只含结构性配置

```ts
interface TestCaseConfig {
  rounds: RoundConfigItem[]
  dimensions: DimensionConfig[]      // 多轮维度（用例级，跨轮聚合）
  background_noise?: BackgroundNoiseConfig  // 用例级背景噪声（可选，轮级优先）
  source_audio?: string
  auto_generated?: boolean
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
  // 独立列（按轮分组）
  algorithm_params?: RoundAlgorithmParams[]
  reference_params?: RoundReferenceParams[]
}
```

### 7. TestCase 接口

```ts
interface TestCase {
  test_type: 'api' | 'e2e'
  config: TestCaseConfig  // 只含结构性配置
  // 独立列（保留，按轮分组）
  algorithm_params?: RoundAlgorithmParams[]
  reference_params?: RoundReferenceParams[]
}
```

## 独立列存储说明

### test_cases.algorithm_params 列（按轮分组）

```ts
// [{round_number, params:[{field_code, field_value}]}]
// 包含：
//   - 输入字段（来自 algorithm_api_params direction=input）
//     例: {field_code:'inputText', field_value:'今天天气怎么样'}
//         {field_code:'inputAudio', field_value:'audio_001'}（多种输入共存）
//   - 用例级配置（来自 case_algorithm_params）
//     例: {field_code:'railDistance', field_value:'50'}
//         {field_code:'voiceprintEnabled', field_value:'true'}
//         {field_code:'interferers', field_value:'[...]'}
```

### test_cases.reference_params 列（按轮分组）

```ts
// [{round_number, reference_params_path}]
// 参考参数内容仍存文件，独立列只存路径
```

## 不变部分

- `TestCaseGroup`、`TestCaseGroupItem` — 不变
- `PlaybackDevice`、`ImportPreviewItem` — 不变
- `AssociatedDimension`、`AlgorithmOption` — 不变
- `DimensionConfig` — 不变（在单轮 evaluation.dimensions 和多轮 dimensions 中使用）

## 引用关系

- ← `02_选用例/backend/03_Config_JSON扁平化设计`
- ← `02_选用例/backend/04_testcase_Schema新类型`
- → `02_选用例/frontend/02_businessTypes适配`
- → `02_选用例/frontend/06_CaseForm_test_type驱动`
- → `02_选用例/frontend/10_RoundConfigEditor`
- → `02_选用例/frontend/12_VoiceprintConfigEditor`
- → `02_选用例/frontend/13_InterfererConfigEditor`
- → `02_选用例/frontend/14_RoundEvaluationEditor`
