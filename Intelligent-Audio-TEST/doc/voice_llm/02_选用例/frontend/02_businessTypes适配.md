# 02_businessTypes 适配（结构性配置 + 独立列参数）

> 文件：`frontend/src/shared/types/businessTypes.ts`
> 状态：本设计文档对应的改造已实现。以下内容已按当前实际代码核对修正，代码摘录后标注实际行号范围。

## 现状分析（改造已落地）

`businessTypes.ts` 是业务类型汇总文件：顶部 import 了 `TestCaseModal/types.ts` 的 rounds-as-top-level 核心类型（`businessTypes.ts:1`），并经 `shared/types/index.ts` 统一 re-export（`index.ts:4-18` 核心类型、`index.ts:28-38` 业务类型）。当前实际状态：

- `TestCase`（业务完整版）采用 `config: TestCaseConfig`，不再内联算法/参考参数，二者回归 `test_cases` 表独立列（按轮分组）；
- `EvaluationDimensionsConfig` 接口仍在文件内（`businessTypes.ts:139-141`），但全项目无任何消费方，属"留存未用"而非删除；
- 设计稿中"给 `Task` 接口新增 `roundProgress`"的适配**未实现**——`businessTypes.ts` 的 `Task` 无该字段，多轮进度实际落在 `useTaskProgress.ts` 内部的 `AssociatedCase` 接口上（详见 §5）。

## 改造方案（结构性配置 + 独立列参数）—— 已实现

### 1. TestCase.config 简化（config 只含结构性配置）

实际定义（`businessTypes.ts:150-170`）：

```ts
export interface TestCase {
    id: string | number;
    name: string;
    description?: string;
    type?: string;
    testType?: string;
    test_type?: 'api' | 'e2e';
    config?: TestCaseConfig;
    /** 按轮分组的算法参数，独立列，对应 test_cases.algorithm_params */
    algorithm_params?: RoundAlgorithmParams[];
    /** 按轮分组的参考参数路径，独立列，对应 test_cases.reference_params */
    reference_params?: RoundReferenceParams[];
    groupId?: string | number;
    groupName?: string;
    tags?: string[] | { id: number; name: string }[];
    algorithmType?: string;
    createdAt?: string;
    updatedAt?: string;
    deleted?: boolean;
    totalDuration?: number;
}
```

> 与设计稿的差异：
> - `id`、`name` 必填，其余字段均可选；设计稿中的必填 `algorithmType: string` **实际非必填**（`algorithmType?: string`），`test_type` 亦为可选；
> - `config` 为 `TestCaseConfig`（可选），详细结构（`rounds?`/`dimensions?`/`voiceprint_config?`/`background_noise?`/`source_audio?`/`auto_generated?` 及索引签名）见 `TestCaseModal/types.ts:200-218`，不在本文件内联；
> - `algorithm_params` / `reference_params` 独立列字段保留，类型为 `RoundAlgorithmParams[]` / `RoundReferenceParams[]`（`TestCaseModal/types.ts:92-95`、`101-104`）；
> - 另保留 `type`/`testType`（旧字段兼容）及 `groupId`/`groupName`/`tags`/`createdAt`/`updatedAt`/`deleted`/`totalDuration` 等展示字段。
> - 注意：`shared/types/index.ts:141-157` 还有一版更宽松的同名表单类型 `TestCaseFormData`（`config?` 可选）。

### 2. RoundConfigItem（只含结构性字段）与独立列参数类型

实际定义（`TestCaseModal/types.ts:83-104`、`188-194`）：

```ts
/**
 * 算法参数项 — 通用算法参数容器
 * 对应后端 AlgorithmParamItem: {field_code, field_value}
 */
export interface AlgorithmParamItem {
  field_code: string;
  field_value: unknown;
}

/**
 * 按轮分组的算法参数 — 对应 test_cases.algorithm_params 列
 * 每个元素描述某一轮的算法参数集合
 */
export interface RoundAlgorithmParams {
  round_number: number;
  params: AlgorithmParamItem[];
}

/**
 * 按轮分组的参考参数路径 — 对应 test_cases.reference_params 列
 * 每个元素描述某一轮的参考参数文件路径
 */
export interface RoundReferenceParams {
  round_number: number;
  reference_params_path: string;
}

/**
 * 单轮配置项 — rounds-as-top-level 架构的核心数据结构
 * 对应后端 RoundConfigItem
 * 仅保留结构性字段：roundNumber, audios, backgroundNoise, evaluation
 */
export interface RoundConfigItem {
  roundNumber: number;
  audios: AudioConfig[];
  backgroundNoise?: BackgroundNoiseConfig;
  evaluation?: RoundEvaluationConfig;
  [key: string]: unknown;
}
```

> **说明**：
> - `AlgorithmParamItem.field_value` 实际类型为 **`unknown`**（设计稿写作 `any`）；
> - `RoundConfigItem.audios` 实际为**必填**（可为空数组，新增空轮时 `createEmptyRound` 写入 `audios: []`，`RoundConfigEditor.vue:224-230`）；实现新增 `[key: string]: unknown` 索引签名（供子编辑器暂存 `round.algorithmParams`/`round.interferers` 等兼容字段，提交时归位）；
> - 各参数存放位置（以下均与设计稿一致，已实现）：
>   - 无 `inputType` 字段（已废弃，多种输入共存）
>   - `inputText`/`inputAudio` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = inputText/inputAudio）
>   - `railDistance`/`volumeLevel` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = railDistance/volumeLevel）
>   - `promptAudioId` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = promptAudioId）
>   - `interferers` 在 `algorithm_params` 独立列对应轮的 params 中（field_code = interferers）
>   - `backgroundNoise` 保留在轮次顶层（E2E 基础环境配置）
>   - `algorithm_params` 独立列格式为 `[{round_number, params:[{field_code, field_value}]}]`，由 `case_algorithm_params` 表驱动
> - 与设计稿的差异：
>   - 设计稿称 `voiceprintRegistration` → `field_code = voiceprintEnabled 等` **已变更**：现行 field_code 为 **`voiceprint` 单对象** `{ audio_id, spl, playback_device_id, voiceprint_wait_time }`（`case_algorithm_params` 中 `param_type: 'audio_select'`，`AlgorithmConfigModal.vue:569`）；旧的 5 个拆分字段（`voiceprintEnabled`/`voiceprintAudioId`/`voiceprintPlaybackDeviceId`/`voiceprintSpl`/`voiceprintWaitTime`）仅为旧数据兼容，前端不进算法参数步骤展示（`sections/AlgoParamsStep.vue:54-63` EXCLUDED_CODES）
>   - 设计稿称 `waitTime` 为独立 field_code **已变更**：`waitTime` 不是独立 field_code，而是 `voiceprint` 对象内的 `voiceprint_wait_time`（单位：秒）；编辑期由 `VoiceprintConfigEditor` 处理，归位时 `CaseForm.syncStructuredFields` 转毫秒写入 `config.voiceprint_config.waitTime`（`CaseForm.vue:612-625`）
>   - 设计稿称 `interferers` 的 `param_type = interferer_list` **实际未实现**：现行为 `param_code='interferers'`、`param_type: 'audio_select'`（`AlgorithmConfigModal.vue:570`）；值为数组或 JSON 字符串两种形态均可解析（`CaseForm.vue:627-646`）

### 3. AudioConfig 适配

`testType` 字段已移除，AudioConfig 作为 `RoundConfigItem.audios[]` 的元素使用。实际定义（`TestCaseModal/types.ts:106-115`）：

```ts
/**
 * 音频配置项 — 轮次内音频
 * testType 已移除，由父级用例的 test_type 决定
 */
export interface AudioConfig {
  audioId: string;
  playbackDeviceId?: string;
  spl?: number;
  playOrder: number;
}
```

> `audioId`、`playOrder` 必填；`playbackDeviceId`、`spl` 为可选（E2E 播放流专用，API 用例如无配置可缺省）。

### 4. EvaluationDimensionsConfig —— 留存未用（未删除）

原设计"用例级评测维度不再存在，改为每轮自带 evaluation.dimensions"的方向正确，但实现并未删除该接口。实际状态（`businessTypes.ts:128-141`）：

```ts
export interface SelectedEvaluationDimension {
    id: number | string;
    name: string;
    weight?: number;
    threshold?: number;
    /** 标记该维度属于哪种 test_type，'api' / 'e2e'，未标记则通用 */
    test_type?: 'api' | 'e2e';
    /** 维度使用范围：'single' = 每轮独立评估，'multi' = 多轮聚合评估。默认 'single' */
    round_scope?: 'single' | 'multi';
}

export interface EvaluationDimensionsConfig {
    dimensions: SelectedEvaluationDimension[];
}
```

> 说明：
> - `EvaluationDimensionsConfig` 定义仍保留在 `businessTypes.ts:139-141`，但全项目**无任何消费方**（Grep 仅命中定义处），属"留存未用"，待后续清理；
> - 维度实际运转方式与设计稿一致：单轮维度存 `RoundConfigItem.evaluation.dimensions`（`RoundEvaluationConfig`，`TestCaseModal/types.ts:140-143`），多轮维度存 `config.dimensions`（`TestCaseConfig.dimensions?: DimensionConfig[]`，`TestCaseModal/types.ts:201`），维度结构为 `DimensionConfig { id?, name, weight, threshold }`（`TestCaseModal/types.ts:120-125`）。

### 5. Task 接口适配 —— 实际未实现

设计稿拟给 `businessTypes.ts` 的 `Task` 增加 `roundProgress`。**该适配实际未实现**——`Task` 至今无该字段（`businessTypes.ts:6-30`）：

```ts
export interface Task {
    id: string | number;
    name: string;
    type: TaskType;
    status: TaskStatus;
    progress: number;
    description?: string;
    createdAt: string;
    updatedAt: string;
    finishedAt?: string;
    error?: string;
    config?: Record<string, any>;
    result?: any;
    tags?: string[];
    caseCount?: number;
    completedCount?: number;
    failedCount?: number;
    totalCases?: number;
    completedCases?: number;
    failedCases?: number;
    deviceCount?: number;
    deleted?: boolean;
    algorithmType?: string;
    algorithmParams?: Record<string, any>;
}
```

> 多轮进度的实际情况：
> - `roundProgress` 实际定义在 `frontend/src/composables/useTaskProgress.ts` **内部**的 `AssociatedCase` 接口上：`RoundProgress { current; total }`（`useTaskProgress.ts:6-9`）、`AssociatedCase.roundProgress?`（`useTaskProgress.ts:11-25`，第 18 行），并在 `handleTaskProgress` 处理 `testCases` 时从 socket 数据映射（`useTaskProgress.ts:190-195`）；
> - 这与 `04_执行测试/frontend/19_useTaskProgress多轮显示.md` 描述的改造一致（该文档正是把 `roundProgress` 加到 `AssociatedCase`，而非 `businessTypes` 的 `Task`）；
> - 结论：`Task`（业务类型）无需改动，本文档 §5 的原设计方案作废。

## 不变部分

以下类型在 `businessTypes.ts` 中仍按原样存在，并经 `shared/types/index.ts:28-38` 统一 re-export：

- `TaskType`（'api' | 'e2e' | 'playback' | 'evaluation' | 'report' | 'task' | 'execution' | 'comparison' | 'performance' | 'stress' | 'audio_import'）、`TaskStatus` — 不变（`businessTypes.ts:3-4`）
- `AudioInfo`、`Audio`、`AudioUploadFile` — 不变（`businessTypes.ts:32-50`、`52-79`）
- `PlaybackDevice` — 不变（`businessTypes.ts:191-205`）
- `APIConfig` — 不变（`businessTypes.ts:172-189`）
- `Report`、`ReportSummary`、`DetailedResult` — 不变（`businessTypes.ts:271-286`、`396-451`、`453-459`）
- 另：`shared/types/index.ts:4-18` 还 re-export 了 `TestCaseModal/types.ts` 的 rounds-as-top-level 核心类型（`AlgorithmParamItem`/`AudioConfig`/`DimensionConfig`/`BackgroundNoiseConfig`/`RoundEvaluationConfig`/`VoiceprintConfig`/`InterfererConfigItem`/`InterruptionConfig`/`RoundConfigItem`/`RoundAlgorithmParams`/`RoundReferenceParams`/`TestCaseConfig`）；
- 同名宽松版 `TestCaseFormData` 定义于 `shared/types/index.ts:141-157`（`config?` 可选，完整版见 `TestCaseModal/types.ts:223-244`），`store/testCaseStore.ts` 使用前者。

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义`
- → `02_选用例/frontend/07_testCaseStore_test_type处理`
- → `04_执行测试/frontend/19_useTaskProgress多轮显示`（实现于 `useTaskProgress.ts` 的 `AssociatedCase`，并非本文件 `Task`，与 §5 已作废的设计无冲突）