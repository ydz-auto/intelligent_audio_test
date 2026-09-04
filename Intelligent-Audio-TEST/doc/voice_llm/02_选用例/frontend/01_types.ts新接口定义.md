# 01_types.ts 新接口定义

> 文件：`frontend/src/components/common/test-case/TestCaseModal/types.ts`
> 状态：本设计文档对应的改造已实现。以下内容已按当前实际代码核对修正，代码摘录后标注实际行号范围。

## 现状分析（改造已落地）

`types.ts` 定义了用例编辑模态窗的类型系统（rounds-as-top-level 架构），当前实际状态：

- 原始设计中 `AudioConfig` 上的 `testType: 'api' | 'e2e'` 字段已移除（由父级用例的 `test_type` 决定）；
- 原始设计中 `config.dimensions: { api: DimensionConfig[], e2e: DimensionConfig[] }` 的形式不存在，当前 `config.dimensions` 为多轮（跨轮聚合）维度数组，单轮维度存于 `RoundConfigItem.evaluation.dimensions`；
- 原始设计中 config 内嵌算法参数/参考参数的形式不存在，二者已移入 `test_cases` 表独立列（`algorithm_params` / `reference_params`，均按轮分组）。

完整定义见下文各节。

## 改造方案（结构性配置 + 独立列参数）—— 已实现

config 只承载结构性配置（rounds/dimensions 等）。算法参数和参考参数回归 `test_cases` 表独立列（按轮分组）。

### 1. AudioConfig 已移除 testType

实际定义（`types.ts:110-115`）：

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

> 注意：`playbackDeviceId`、`spl` 为可选字段。二者注释标注 E2E 专用（E2E 播放流才需要设备与声压），API 用例如无配置可缺省。

### 2. BackgroundNoiseConfig 已新增 loop

实际定义（`types.ts:130-135`）：

```ts
/**
 * 背景噪声配置 — 新增 loop 字段
 */
export interface BackgroundNoiseConfig {
  audioId: string;
  deviceIds: string[];
  spl: number;
  loop?: boolean;
}
```

> 注意：`loop` 为**可选**布尔，表示循环播放（true）/播完自然结束（false）。
> 编辑器（`sections/NoiseInterferenceStep.vue`）默认按 `round.backgroundNoise?.loop ?? false` 渲染；
> 批量更新噪声（`store/testCaseStore.ts` `batchUpdateNoise`）写入 `loop: false`；
> 旧版 flat 配置转换（`utils/utils.ts` normalizeTestCaseConfig）同样写入 `loop: false`。

### 3. RoundConfigItem — 轮次配置（核心接口，只含结构性字段）

> **设计原则：结构性配置与参数分离（已实现）**
>
> RoundConfigItem 只保留结构性字段。算法参数和参考参数不在 config.rounds[] 中，
> 分别存 `test_cases.algorithm_params` 和 `test_cases.reference_params` 独立列（按轮分组）。
> 算法参数由 `case_algorithm_params` 表定义驱动，DynamicForm 动态渲染。

实际定义（`types.ts:83-104`、`types.ts:188-194`）：

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
 */
export interface RoundConfigItem {
  roundNumber: number;                  // 轮次序号（前端自动编号）
  audios: AudioConfig[];                // 本轮音频列表（必填，可为空数组）
  backgroundNoise?: BackgroundNoiseConfig;  // E2E 基础环境配置（轮次顶层）
  evaluation?: RoundEvaluationConfig;   // 本轮评估配置
  [key: string]: unknown;               // 索引签名（兼容临时/非结构化字段）
}
```

> 与设计稿的差异：`audios` 为**必填**（新增空轮时 `createEmptyRound` 写入 `audios: []`，见 `RoundConfigEditor.vue:224-230`）；实现新增了 `[key: string]: unknown` 索引签名（供子编辑器暂存 `round.algorithmParams`、`round.interferers` 等兼容字段，提交时再归位）。

### 4. 子配置接口（DynamicForm 子编辑器的数据结构）

> 以下接口不再直接作为 RoundConfigItem 的子字段，而是作为专门编辑器/DynamicForm 复杂参数
> 的数据结构。例如声纹编辑器使用 `VoiceprintConfig`（值承载于 `field_code='voiceprint'` 的 field_value），
> 干扰人编辑器使用 `InterfererConfigItem`（值承载于 `field_code='interferers'` 的 field_value），
> 二者均存储在 `test_cases.algorithm_params` 列对应轮的 params 中。

实际定义（`types.ts:149-177`）：

```ts
/**
 * 声纹注册配置（数据层）
 * 在 algorithmParams 中拆分为多个 field_code
 */
export interface VoiceprintConfig {
  enabled: boolean;
  audioId?: string;
  playbackDeviceId?: string;
  spl: number;
  waitTime: number;
}

/**
 * 单个干扰人配置
 */
export interface InterfererConfigItem {
  audioId?: string;
  audioName?: string;
  playbackDeviceId?: string;
  /** 设备名（统一标注文件导入时无 ID，仅设备名） */
  playbackDeviceName?: string;
  spl: number;
  startDelay: number;
  loop: boolean;
}

/**
 * 轮次评估配置
 */
export interface RoundEvaluationConfig {
  enabled: boolean;
  dimensions: DimensionConfig[];  // 单轮维度
}

/**
 * 打断检测配置
 */
export interface InterruptionConfig {
  enabled: boolean;
  sensitivity: number;
}
```

> 与设计稿的差异：
> - `VoiceprintConfig.spl`、`waitTime` 实际为**必填**（设计稿为可选）。
> - `InterfererConfigItem` 实际**无 `id` 字段**，且 `audioId`/`playbackDeviceId` 为可选；
>   新增 `audioName`（干扰音频文件名）与 `playbackDeviceName`（设备名）——统一标注文件导入时无 ID、仅文件名/设备名，保存后由后端按名称解析。
> - 编辑器与 field_code 映射：声纹 → `VoiceprintConfigEditor.vue`（常量 `VOICEPRINT_CODE = 'voiceprint'`，`VoiceprintConfigEditor.vue:162`），干扰人 → `sections/NoiseInterferenceStep.vue`（内部使用 `InterfererConfigEditor.vue`）。
>   设计稿中 "param_type=interferer_list" 的说法**实际未实现**——现行 param 定义为 `param_code='interferers'`（`param_type: 'audio_select'`，见 `components/algorithm/AlgorithmConfigModal.vue:570`）。

### 5. TestCaseConfig — config 只含结构性配置

实际定义（`types.ts:196-218`）：

```ts
/**
 * 测试用例配置 — rounds-as-top-level 架构
 * config = { rounds: [...], dimensions: [...] }
 */
export interface TestCaseConfig {
  rounds?: RoundConfigItem[];
  dimensions?: DimensionConfig[];      // 多轮维度（用例级，跨轮聚合）
  voiceprint_config?: {
    enabled?: boolean;
    audio?: { id?: string };
    device?: { id?: string };
    spl?: number;
    waitTime?: number;
  };
  /** case 级全局背景噪声（跨所有轮次持续播放，优先于 round 级） */
  background_noise?: BackgroundNoiseConfig;   // 用例级背景噪声（可选，轮级优先）
  /** 源音频路径 */
  source_audio?: string;
  /** 是否自动生成 */
  auto_generated?: boolean;
  [key: string]: unknown;
}
```

> 与设计稿的差异：`rounds`、`dimensions` 实际为**可选**；实现新增 `voiceprint_config`（case 级声纹注册配置，由 `CaseForm.syncStructuredFields` 从 `algorithm_params` 的 `voiceprint` 参数同步写入，`CaseForm.vue:612-625`）及 `[key: string]: unknown` 索引签名。

### 6. TestCaseFormData

实际定义（`types.ts:220-244`）：

```ts
/**
 * 表单数据 — 包含 test_type
 */
export interface TestCaseFormData {
  id?: string | number;
  name: string;
  description?: string;
  group?: string;
  groupId?: string | number;
  group_id?: string;
  groupName?: string;
  group_name?: string;
  tags?: string[];
  tagsInput?: string;
  test_type?: 'api' | 'e2e';
  algorithmType?: string;
  algorithm_type?: string;
  config: TestCaseConfig;
  /** 按轮分组的算法参数，独立于 config，对应 test_cases.algorithm_params 列 */
  algorithm_params?: RoundAlgorithmParams[];
  /** 按轮分组的参考参数路径，独立于 config，对应 test_cases.reference_params 列 */
  reference_params?: RoundReferenceParams[];
  _originalGroup?: string;
  _originalGroupId?: string;
}
```

> 与设计稿的差异：`test_type` 实际为**可选**（`CaseForm` 初始化时 `forcedTestType || raw.test_type || 'api'`）；`groupId` 类型为 `string | number`；
> 实现额外补充了 `group_id`/`groupName`/`group_name`/`tagsInput`/`algorithm_type` 等兼容字段，以及 `_originalGroup`/`_originalGroupId`。
> 另注意：`shared/types/index.ts:141-157` 还存在一版更宽松的同名 `TestCaseFormData`（字段更少、`config?` 可选），`store/testCaseStore.ts` 从 `../shared/types` 导入的是该版本。

### 7. TestCase 接口

`types.ts` 内的 `TestCase`（`types.ts:28-40`）是轻量展示接口，**不含**设计稿中的 `algorithm_params`/`reference_params`：

```ts
export interface TestCase {
  id?: string | number;
  name?: string;
  group_name?: string;
  group?: string;
  groupName?: string;
  group_id?: string | number;
  groupId?: string | number;
  type?: string;
  testType?: string;
  test_type?: 'api' | 'e2e';
  config?: TestCaseConfig;
}
```

> 设计稿中带独立列的完整 `TestCase`（`algorithm_params?` / `reference_params?` 等）实际定义在
> `frontend/src/shared/types/businessTypes.ts:150-170`，见 `02_businessTypes适配.md` §1。

## 独立列存储说明（已实现）

### test_cases.algorithm_params 列（按轮分组）

```ts
// [{round_number, params:[{field_code, field_value}]}]
// RoundAlgorithmParams[]，见 types.ts:92-95
```

实际包含的 field_code（以内置参数预设为准，见 `components/algorithm/AlgorithmConfigModal.vue:561-576` PARAM_CODE_PRESETS）：

- 输入字段（来自 algorithm_api_params direction=input）：
  - `inputText` — 输入文本（如 `{field_code:'inputText', field_value:'今天天气怎么样'}`）
  - `inputAudio` — 输入音频（多种输入可共存）
- 用例级配置（来自 case_algorithm_params）：
  - `railDistance` / `volumeLevel` — 环境设备参数
  - `voiceprint` — 声纹注册，值为**单个对象** `{ audio_id, spl, playback_device_id, voiceprint_wait_time }`
    （由 `VoiceprintConfigEditor.vue` 编辑；`case_algorithm_params` 中该参数 `param_type: 'audio_select'`）
  - `interferers` — 干扰人列表，值为数组或 JSON 字符串（`CaseForm.syncStructuredFields` 兼容两种形态，`CaseForm.vue:628-643`）
  - `promptAudioId` / `asr_ref` / `tran_ref` / `overlap_rate` / `overlap_time` / `translation_direction` / `source_language` / `target_language` 等
- 旧格式兼容：数据库可能仍存有旧的 5 个拆分字段 `voiceprintEnabled` / `voiceprintAudioId` / `voiceprintPlaybackDeviceId` / `voiceprintSpl` / `voiceprintWaitTime`，
  前端不进算法参数步骤展示（`sections/AlgoParamsStep.vue:54-63` EXCLUDED_CODES），现行统一为 `voiceprint` 单对象。
- 编辑期间数据流：`RoundConfigEditor` 按 `round_number` 从独立列读取/写回本轮的 params（`RoundConfigEditor.vue:171-190`）；
  提交时 `utils/utils.ts` `convertTestCaseFormData` 会把独立列归一化并移除 `round.algorithmParams` 临时字段（`utils.ts:353-401`）。

### test_cases.reference_params 列（按轮分组）

```ts
// [{round_number, reference_params_path}]
// 参考参数内容仍存文件，独立列只存路径（RoundReferenceParams，见 types.ts:101-104）
```

- 轮次编辑器中由 `sections/ReferencePathStep.vue` 只读展示（自动生成），提交时从 `round.referenceParamsPath` 提取进独立列（`utils.ts:403-443`）。

## 不变部分

- `TestCaseGroup`、`TestCaseGroupItem` — 不变（`types.ts:1-12`，另有 `GroupStat` `types.ts:14-19`）
- `PlaybackDevice`、`ImportPreviewItem` — 不变（`types.ts:52-56`、`58-63`）
- `AssociatedDimension`、`AlgorithmOption` — 不变（`types.ts:264-277`）
- `DimensionConfig` — 不变（`types.ts:120-125`：`{ id?: string | number; name: string; weight: number; threshold: number }`，在单轮 `evaluation.dimensions` 和多轮 `config.dimensions` 中使用）

## 引用关系

- ← `02_选用例/backend/03_Config_JSON扁平化设计`
- ← `02_选用例/backend/04_testcase_Schema新类型`
- → `02_选用例/frontend/02_businessTypes适配`
- → `02_选用例/frontend/06_CaseForm_test_type驱动`
- → `02_选用例/frontend/10_RoundConfigEditor`
- → `02_选用例/frontend/12_VoiceprintConfigEditor`
- → `02_选用例/frontend/13_InterfererConfigEditor`
- → `02_选用例/frontend/14_RoundEvaluationEditor`