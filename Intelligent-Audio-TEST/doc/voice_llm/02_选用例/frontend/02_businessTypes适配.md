# 02_businessTypes 适配（结构性配置 + 独立列参数）

> 文件：`frontend/src/shared/types/businessTypes.ts`

## 改造方案

### 1. TestCase.config 简化（config 只含结构性配置）

```ts
interface TestCase {
  id: string | number
  name: string
  algorithmType: string

  config: {
    rounds: RoundConfigItem[]
    dimensions: DimensionConfig[]          // 多轮维度
    background_noise?: BackgroundNoiseConfig  // 用例级
    source_audio?: string
    auto_generated?: boolean
  }

  test_type: 'api' | 'e2e'

  // 独立列（保留，按轮分组）
  algorithm_params?: RoundAlgorithmParams[]
  reference_params?: RoundReferenceParams[]
}
```

### 2. RoundConfigItem（只含结构性字段）

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
  roundNumber: number
  audios?: AudioConfig[]
  backgroundNoise?: BackgroundNoiseConfig
  evaluation?: RoundEvaluationConfig
  // 算法参数和参考参数不在 config.rounds[] 中：
  // - algorithm_params → test_cases.algorithm_params 独立列（按轮分组）
  // - reference_params → test_cases.reference_params 独立列（按轮分组）
}
```

> **说明**：
> - 无 `inputType` 字段（已废弃，多种输入共存）
> - `inputText`/`inputAudioId`/`audioId` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = inputText/inputAudio）
> - `waitTime` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = waitTime）
> - `railDistance`/`volumeLevel` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = railDistance/volumeLevel）
> - `voiceprintRegistration` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = voiceprintEnabled 等）
> - `promptAudioId` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = promptAudioId）
> - `interferers` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = interferers）
> - `backgroundNoise` 保留在轮次顶层（E2E 基础环境配置）
> - `algorithm_params` 独立列格式为 `[{round_number, params:[{field_code, field_value}]}]`，由 `case_algorithm_params` 表驱动

### 3. AudioConfig 适配

移除 `testType` 字段。AudioConfig 现在作为 `RoundConfigItem.audios[]` 的内嵌结构使用。

### 4. EvaluationDimensionsConfig 废弃

用例级评测维度不再存在。每轮自带 `evaluation.dimensions`（单轮维度），`config.dimensions` 存多轮维度。

### 5. Task 接口适配

```ts
interface Task {
  progress: number
  roundProgress?: {
    current: number
    total: number
  }
}
```

## 不变部分

- `TaskType` 联合类型 — 不变
- `AudioInfo`、`Audio`、`AudioUploadFile` — 不变
- `PlaybackDevice`、`APIConfig` — 不变
- `Report`、`ReportSummary`、`DetailedResult` — 不变

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义`
- → `02_选用例/frontend/07_testCaseStore_test_type处理`
- → `04_执行测试/frontend/19_useTaskProgress多轮显示`
