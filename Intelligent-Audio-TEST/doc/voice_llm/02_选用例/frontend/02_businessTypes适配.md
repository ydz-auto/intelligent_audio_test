# 02_businessTypes 适配（轮次为顶层）

> 文件：`frontend/src/shared/types/businessTypes.ts`

## 改造方案

### 1. TestCase.config 简化（config 只剩 rounds + dimensions）

```ts
interface TestCase {
  id: string | number
  name: string
  algorithmType: string

  config: {
    rounds: RoundConfigItem[]
    dimensions: DimensionConfig[]
    // 废弃：audios, backgroundNoise, voiceprintRegistration,
    // interferers, roundEvaluation, railDistance, volumeLevel, promptAudioId, interruption
  }

  test_type: 'api' | 'e2e'

  // 废弃列（过渡期保留）
  // reference_params → 文件 + config.rounds[].referenceParamsPath
  // algorithm_params → config.rounds[].algorithmParams
}
```

### 2. RoundConfigItem（完整结构）

```ts
interface AlgorithmParamItem {
  field_code: string
  field_value: any
}

interface RoundConfigItem {
  roundNumber: number
  audios?: AudioConfig[]
  backgroundNoise?: BackgroundNoiseConfig

  evaluation?: RoundEvaluationConfig

  referenceParamsPath?: string
  algorithmParams?: AlgorithmParamItem[]
}
```

> **说明**：
> - 无 `inputType` 字段（已废弃，多种输入共存）
> - `inputText`/`inputAudioId`/`audioId` 移入 `algorithmParams`（field_code = inputText/inputAudio）
> - `waitTime` 移入 `algorithmParams`（field_code = waitTime）
> - `railDistance`/`volumeLevel` 移入 `algorithmParams`（field_code = railDistance/volumeLevel）
> - `voiceprintRegistration` 移入 `algorithmParams`（field_code = voiceprintEnabled 等）
> - `promptAudioId` 移入 `algorithmParams`（field_code = promptAudioId）
> - `interferers` 移入 `algorithmParams`（field_code = interferers）
> - `backgroundNoise` 保留在轮次顶层（E2E 基础环境配置）
> - `algorithmParams` 格式为 `[{field_code, field_value}]` 数组，由 `case_algorithm_params` 表驱动

### 3. AudioConfig 适配

移除 `testType` 字段。AudioConfig 现在作为 `RoundConfigItem.audios[]` 的内嵌结构使用。

### 4. EvaluationDimensionsConfig 废弃

用例级评测维度不再存在。每轮自带 `evaluation.dimensions`。

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
