# TestCaseModal - 测试用例表单适配方案

## 1. 组件概述

### 1.1 组件定位
TestCaseModal 是测试用例创建/编辑的核心弹窗组件，已按算法配置化方案完成适配。组件以目录形式实现于 `frontend/src/components/common/test-case/TestCaseModal/`（`index.vue` 按 mode 分发 GroupForm/CaseForm/ImportForm/ExportForm，用例表单主体为 `CaseForm.vue`），由测试用例管理页面（`views/TestCaseManager.vue` + `store/testCaseStore.ts`）驱动。

> **命名说明**：`test-case/AddTestCaseModal.vue` 是另一个组件——"中途新增测试用例"时从已有用例列表中勾选的弹窗，不含表单字段，与本方案所述创建/编辑表单无关。

### 1.2 使用场景
- 新建测试用例
- 编辑测试用例
- 复制测试用例

### 1.3 核心改动（已实施）
- 算法类型选择：集成 `AlgorithmSelector` 组件（单选模式），算法选项来自 `useAlgorithmConfig().getAlgorithmOptions()`
- 算法参数按轮编辑：参数不再内嵌于 `config.rounds[]`，保存到 `test_cases.algorithm_params` 独立列（按轮分组）
- 评估维度按算法过滤：通过 `useDimensions().fetchDimensionsByAlgorithmType()` 加载关联维度

### 1.4 分层与命名口径
后端所有响应经 `success_response` 统一转换为 camelCase；前端遵循 DDD 分层——Presentation（views/components）只见 camelCase Domain 与 composables（Ports），`utils/api.ts`（Infrastructure）是唯一感知 snake_case 的层。用例执行的执行方式由被测设备 `device_type` 路由三执行器（物理设备→E2EExecutor、HTTP API→APISessionExecutor、WebSocket API→RealtimeSessionExecutor）；"api/e2e 为独立用例记录的 test_type 决定执行方式"属废弃口径。

---

## 2. 用例与算法的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         用例与算法的关系                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  TestCase ──────算法类型─────→ AlgorithmDefinition                       │
│       │                                                                   │
│       │  test_cases.algorithm_type = 'translation'   （独立列）          │
│       │                                                                   │
│       │  test_cases.algorithm_params = [                                 │
│       │    { round_number: 1,                                            │
│       │      params: [                                                   │
│       │        { field_code: 'translation_direction',                    │
│       │          field_value: 'zh2en' }   ← 取值由 CaseAlgorithmParam   │
│       │      ]                              与 formSchema 约束          │
│       │    }                                                             │
│       │  ]                                            （独立列，按轮分组）│
│                                                                          │
│  工作流程（已实施）：                                                      │
│  1. 新建用例时，AlgorithmSelector 选择算法类型                            │
│  2. 根据算法类型加载 case_algorithm_params 与 formSchema（带缓存）        │
│  3. 用户在 RoundConfigEditor 中按轮填写参数，                             │
│     保存到 algorithm_params 独立列（不写入 config）                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  新建/编辑测试用例                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  基本信息:                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  用例名称: [________________________]                          │   │
│  │  算法类型: [翻译 ▼] ← 选择算法类型（新增）                       │   │
│  │  用例描述: [__________________________________________]        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  算法参数配置: (选择算法后，根据 AlgorithmConfigPage 配置动态渲染)          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ▶ 基本配置                                                      │   │
│  │    翻译方向: [中译英 ▼] ← DynamicForm 渲染                      │   │
│  │                                                                │   │
│  │                                                                │   │
│  │  ▶ 高级选项 (可折叠)                                             │   │
│  │    置信度阈值: [━━━●━━━━] 0.8                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  音频配置: (现有功能)                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 添加音频]                                                    │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  音频1.wav  │  时长: 5.2s  │  [播放] [删除]               │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  评估维度: (根据算法类型过滤)                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  [+ 添加评估维度] ← 只显示该算法关联的评估维度                    │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  BLEU评分  │  阈值: >0.8  │  [删除]                       │ │   │
│  │  │  ROUGE评分 │  阈值: >0.7  │  [删除]                       │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│                                [取消] [保存]                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据结构

> **命名口径**：后端列与 DTO 为 snake_case，经 `success_response` 统一转换后前端收到 camelCase；前端 Presentation 层只见 camelCase Domain。

### 4.1 表单数据结构（已实施，见 TestCaseModal/types.ts）

```typescript
interface TestCaseFormData {
  id?: string | number;
  name: string;
  description?: string;
  group?: string;
  groupId?: string | number;
  tags?: string[];
  test_type?: 'api' | 'e2e';      // 用例记录分类；执行方式由被测设备 device_type 路由，此字段不决定执行方式
  algorithmType?: string;          // 算法类型（camelCase）
  config: TestCaseConfig;          // 仅结构性配置（见 4.2）
  // 独立列，与 config 平级，不内嵌于 config：
  algorithm_params?: RoundAlgorithmParams[];    // 按轮分组算法参数 → test_cases.algorithm_params
  reference_params?: RoundReferenceParams[];    // 按轮分组参考参数路径 → test_cases.reference_params
}

// 按轮分组的算法参数，对应 test_cases.algorithm_params 列
interface RoundAlgorithmParams {
  round_number: number;
  params: AlgorithmParamItem[];    // { field_code, field_value }，对应后端 AlgorithmParamItem
}

// 按轮分组的参考参数路径，对应 test_cases.reference_params 列
interface RoundReferenceParams {
  round_number: number;
  reference_params_path: string;
}
```

### 4.2 TestCaseConfig 结构（仅结构性配置，已实施）

`config` 只承载结构性配置；算法参数与参考参数是独立列，**不在 config 中**（后端 `schemas/testcase.py` 的 `TestCaseConfig` 与前端 `TestCaseModal/types.ts` 口径一致）：

```typescript
interface TestCaseConfig {
  rounds?: RoundConfigItem[];              // 轮次数组（rounds-as-top-level）
  dimensions?: DimensionConfig[];          // 整体评估维度（多轮聚合）
  voiceprint_config?: {...};               // 声纹注册配置
  background_noise?: BackgroundNoiseConfig;// case 级全局背景噪声（优先于轮次级）
  source_audio?: string;                   // 源音频路径
  auto_generated?: boolean;                // 是否自动生成
}

// 单轮配置项仅保留结构性字段，算法参数/参考参数已移至独立列
interface RoundConfigItem {
  roundNumber: number;
  audios: AudioConfig[];                   // { audioId, playbackDeviceId, spl, playOrder }
  backgroundNoise?: BackgroundNoiseConfig;
  evaluation?: RoundEvaluationConfig;      // 轮次级评估维度
}
```

后端对应 `TestCaseListItem`/`TestCaseDetailData` 中 `algorithm_params`、`reference_params`、`algorithm_type` 与 `config` 平级返回。

### 4.3 用例特殊字段（已废弃，归并说明）

原方案的 `TestCaseSpecialFields`（case_id/case_name/device_id/algorithm_type/source_lang/target_lang 等嵌套于 config）**已废弃**，现状归并方式：

- 用例标识（id/name）、算法类型：均为 `test_cases` 表顶层独立字段，不进 special_fields
- 分组标签：`tags` 独立字段
- 语言方向等算法语义字段：作为算法参数项 `{ field_code, field_value }` 存入 `algorithm_params` 独立列，取值范围由 `CaseAlgorithmParam` 与 formSchema 定义
- 声纹/干扰人等复合配置：在 `CaseForm.vue` 中从 algorithmParams 按-field_code 同步到 `voiceprint_config`、`interferers` 等结构化字段

---

## 5. 组件设计

### 5.1 组件结构（已实施）

```
components/common/test-case/TestCaseModal/
├── index.vue                    # 弹窗壳，按 mode 分发 group/case/import/export 四类表单
├── CaseForm.vue                 # 用例表单主体（算法选择 + 轮次配置 + 全局噪声 + 整体维度）
├── RoundConfigEditor.vue        # 轮次配置编辑器（替换旧的音频/噪声/维度三大区块）
├── OverallEvaluationEditor.vue  # 整体评估维度编辑器（多轮聚合，config.dimensions）
├── AudioSelectEditor.vue        # 轮内音频选择编辑器
├── sections/ReferencePathStep.vue # 参考参数路径步骤（reference_params 独立列）
├── useDimensionConfig.ts        # 维度加载/过滤/勾选 composable（组件内局部状态）
└── types.ts                     # rounds-as-top-level 核心类型定义

依赖的上层组件与 composables：
├── AlgorithmSelector.vue        # 算法类型选择器（components/common/）
├── composables/useAlgorithmConfig.ts   # 算法选项/case 参数/formSchema（带缓存）
├── composables/useAlgorithmLabels.ts   # 算法标签回退选项
├── composables/useDimensions.ts        # fetchAllDimensions / fetchDimensionsByAlgorithmType
└── store/testCaseStore.ts              # 保存用例与 algorithm_params（testcasesApi）
```

### 5.2 核心模板（CaseForm.vue 实际结构摘要）

```vue
<template>
  <div class="case-form">
    <!-- 基本信息：用例名称（支持按标签自动生成）/ 所属分组 / 标签（搜索+分页）/ 描述 -->

    <!-- 算法类型选择（单选，show-params=false 时参数由轮次编辑器承载） -->
    <AlgorithmSelector
      v-if="!isTestTypeLocked"
      v-model="localFormData.algorithmType"
      :initial-params="algorithmParams"
      :single="true"
      :show-params="false"
      @params-change="handleAlgorithmParamsChange"
      @algorithm-type-change="handleAlgorithmTypeChange"
    />

    <!-- test_type 切换器（API/E2E，仅用例管理页面显示） -->
    <!-- 轮次配置编辑器：结构性轮次 + 按轮算法参数 -->
    <RoundConfigEditor
      v-model="localFormData.config.rounds"
      :test-type="localFormData.test_type || 'api'"
      :case-algorithm-params="caseAlgorithmParams"
      :algorithm-type="localFormData.algorithmType"
      :algorithm-form-schema="algorithmFormSchema"
      :algorithm-params="localFormData.algorithm_params"
      @update:algorithm-params="handleAlgorithmParamsUpdate"
    />

    <!-- 全局背景噪声（config.background_noise，跨轮次持续播放，优先于轮次级） -->

    <!-- 整体评估维度（config.dimensions，多轮时显示，按算法类型过滤） -->
    <OverallEvaluationEditor
      v-model="localFormData.config.dimensions"
      :available-dimensions="availableDimensions"
      :algorithm-type="localFormData.algorithmType"
    />
  </div>
</template>
```

> 弹窗外壳由 `index.vue` 提供（teleport + modal-container），底部统一"取消/提交"按钮，不使用 Element UI 的 el-dialog。

---

## 6. 核心交互逻辑

### 6.1 算法类型切换（已实施）

```typescript
// CaseForm.vue：算法选项与参数定义来自 useAlgorithmConfig（带缓存，Port 编排）
const { getAlgorithmOptions, getCaseAlgorithmParams: fetchCaseAlgorithmParams } = useAlgorithmConfig();
const { algorithmOptions: fallbackOptions, loadAlgorithms } = useAlgorithmLabels();

// AlgorithmSelector 选择/切换算法类型时触发
function handleAlgorithmTypeChange(newType: string) {
  localFormData.value.algorithmType = newType;
  // 触发加载该算法的 case_algorithm_params 与 formSchema
}

// AlgorithmSelector params-change 返回参数定义与表单 schema
function handleAlgorithmParamsChange(params: any) {
  algorithmParams.value = params || {};
  if (params?.caseAlgorithmParams) {
    caseAlgorithmParams.value = params.caseAlgorithmParams;   // CaseAlgorithmParam 列表
  }
  if (params?.algorithmFormSchema !== undefined) {
    algorithmFormSchema.value = params.algorithmFormSchema;   // formSchema（camelCase）
  }
}
```

评估维度联动：算法类型变化时由 `useDimensionConfig().updateAssociatedDimensions(algorithmType)` 调用 `useDimensions().fetchDimensionsByAlgorithmType()` 刷新关联维度。

### 6.2 参数变化处理（独立列口径，已实施）

```typescript
// RoundConfigEditor 内按轮编辑参数，写回独立列（不写入 config）
function handleAlgorithmParamsUpdate(params: any[]) {
  localFormData.value.algorithm_params = params;   // [{ round_number, params: [{field_code, field_value}] }]
}

// 编辑期间兼容：若独立列缺失，从 round.algorithmParams 回退读取（子组件过渡态）
```

### 6.3 保存用例（已实施）

```typescript
// 保存由 testCaseStore 统一编排（Application 层），经 testcasesApi（Infrastructure）提交：
// - 新建/更新用例：algorithm_params 作为独立参数随用例保存
// - 批量更新参数：testcasesApi.batchAction('update_algorithm_params', ids, payload)
// 保存前将参数归一化为 camelCase，避免合并后新旧键共存（algorithmParams vs algorithm_params）
// 声纹/干扰人参数从 algorithmParams 按 field_code 同步到 voiceprint_config / interferers 结构化字段
```

### 6.4 编辑时加载数据（已实施）

```typescript
// CaseForm.vue loadEditData 摘要：
// 1. 算法类型兼容读取：raw.algorithmType || raw.algorithm_type
// 2. 参数独立列兼容读取：raw.algorithmParams || raw.algorithm_params（按轮分组数组）
// 3. 从独立列按 round_number 取第一轮 params，作为 AlgorithmSelector 的 initial-params（单轮编辑器）
// 4. 若有算法类型，联动加载 caseAlgorithmParams / algorithmFormSchema / 关联维度
```

---

## 7. 不同算法类型的参数配置示例

### 7.1 翻译算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (翻译)                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    翻译方向: [中译英 ▼]                                                  │
│              选项: 中译英、英译中、中日互译、中韩互译等                     │
│                                                                          │
│  ▶ 高级选项                                                              │
│    源语言:   [zh        ] (隐藏字段)                                     │
│    目标语言: [en        ] (隐藏字段)                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 ASR 算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (ASR)                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    参考文本: [________________________________]                          │
│              用于 ASR 识别结果对比                                       │
│                                                                          │
│  ▶ 模型配置                                                              │
│    采样率:   [16kHz ▼]                                                   │
│              选项: 8kHz, 16kHz, 44.1kHz                                  │
│    模型大小: [base ▼]                                                    │
│              选项: tiny, base, small, medium, large                      │
│                                                                          │
│  ▶ 高级选项                                                              │
│    语言:     [中文 ▼]                                                    │
│    置信度阈值: [━━━●━━━━] 0.8                                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.3 声纹识别算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (声纹识别)                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    重叠率:   [━━━━━●━━━━] 50%                                            │
│              前后语音重叠播放的比例                                       │
│                                                                          │
│  ▶ 模型配置                                                              │
│    相似度阈值: [━━━━●━━━━━] 0.7                                          │
│              说话人相似度判定阈值                                         │
│                                                                          │
│  ▶ 高级选项                                                              │
│    采样率:   [16kHz ▼]                                                   │
│    声纹模型: [ecapa-tdnn ▼]                                              │
│              选项: ecapa-tdnn, resnet, x-vector                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.4 TTS 算法参数

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置 (TTS)                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 基本配置                                                              │
│    源语言:   [中文 ▼]                                                    │
│    源文本:   [________________________________]                          │
│              需要合成的文本内容                                           │
│                                                                          │
│  ▶ 模型配置                                                              │
│    语音模型: [女声-温柔 ▼]                                               │
│              选项: 女声-温柔, 女声-活泼, 男声-沉稳, 男声-阳光             │
│    语速:     [━━━●━━━━] 1.0x                                             │
│    音量:     [━━━━●━━━] 80%                                              │
│                                                                          │
│  ▶ 高级选项                                                              │
│    采样率:   [16kHz ▼]                                                   │
│    输出格式: [WAV ▼]                                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 评估维度联动

### 8.1 维度过滤逻辑（已实施，见 useDimensionConfig.ts）

```typescript
// TestCaseModal/useDimensionConfig.ts：维度加载与按算法过滤
const { fetchAllDimensions, fetchDimensionsByAlgorithmType } = useDimensions();

async function loadDimensions(algorithmType?: string) {
  // 有算法类型：按算法关联维度加载；否则全量加载（forceRefresh）
  const dimensions = algorithmType
    ? await fetchDimensionsByAlgorithmType(algorithmType)
    : await fetchAllDimensions({ forceRefresh: true });
  availableDimensions.value = dedupeByName(dimensions);
}

async function updateAssociatedDimensions(algorithmType: string) {
  // 算法关联维度（AlgorithmDimensionRelation），供过滤候选集
  const dimensions = await fetchDimensionsByAlgorithmType(algorithmType);
  associatedDimensions.value = dimensions.map(d => ({ id: d.id, name: d.name, weight: 50, is_default: false }));
}

// 关联维度非空时，候选维度收敛为关联集合
const filteredAvailableDimensions = computed(() => {
  if (!associatedDimensions.value.length) return availableDimensions.value;
  const ids = new Set(associatedDimensions.value.map(d => d.id));
  return availableDimensions.value.filter(dim => ids.has(dim.id));
});
```

### 8.2 维度选择与默认值

```typescript
// 勾选/取消维度（DimensionConfig: { id, name, weight, threshold }）
function toggleDimensionSelection(dimension: Dimension, dimensions: DimensionConfig[]) {
  const index = dimensions.findIndex(dim => dim.name === dimension.name);
  if (index > -1) dimensions.splice(index, 1);
  else dimensions.push({ id: dimension.id, name: dimension.name, weight: 50, threshold: 80 });
}

// 轮次级维度写入 round.evaluation.dimensions，多轮聚合维度写入 config.dimensions
// （OverallEvaluationEditor 仅在 rounds.length > 1 时显示）
```

---

## 9. 表单验证规则

### 9.1 基本验证规则

用例名称、所属分组为必填（原生表单 `required` 校验 + 提交前检查）；算法类型为可选（不选则不渲染参数编辑区）。

### 9.2 动态验证

动态参数验证由配置驱动，不硬编码规则：

- `formSchema` 字段的 `required` 标记必填项（fieldCode/fieldName/component 均为 camelCase）
- `CaseAlgorithmParam` 的 `min_value`/`max_value`/`step` 约束数值范围，经统一 camelCase 转换后为 `minValue`/`maxValue`/`step`
- 早期方案中的 `field.validation.pattern` 结构已废弃——formSchema 字段不含 validation 嵌套对象，范围约束统一由 CaseAlgorithmParam 承载

---

## 10. 状态管理

### 10.1 状态归属（已实施）

| 状态 | 归属层 | 说明 |
|------|--------|------|
| `localFormData`（TestCaseFormData） | Presentation（CaseForm.vue） | 表单编辑态，含 config、algorithmType、algorithm_params 独立列 |
| `algorithmParams` / `caseAlgorithmParams` / `algorithmFormSchema` | Presentation（CaseForm.vue） | 算法参数定义与 schema，来自 useAlgorithmConfig |
| `availableDimensions` / `associatedDimensions` | Presentation（useDimensionConfig.ts） | 维度候选集与关联集 |
| 用例列表、保存/批量动作 | Application（testCaseStore.ts） | 编排 testcasesApi，缓存 ReadModel，保存前归一化 camelCase |
| 算法选项/参数/formSchema 缓存 | Application（useAlgorithmConfig.ts） | formSchemas Map + caseParamCache 缓存 |

### 10.2 初始状态（已实施）

```typescript
// CaseForm.vue createEmptyFormData 摘要
{
  name: '',
  description: '',
  group: '',
  tags: [],
  test_type: 'api',
  algorithmType: '',
  config: { rounds: [], dimensions: [] },
  algorithm_params: [],   // 独立列，初始为空数组（按轮分组）
  reference_params: []    // 独立列，初始为空数组（按轮分组）
}
```

---

## 11. 实施清单（已完成）

### 11.1 后端实施

- [x] TestCase 顶层 `algorithm_type` 字段与 `algorithm_params`/`reference_params` 独立列（`schemas/testcase.py`：与 config 平级，algorithm_params 按轮分组）
- [x] 用例保存/批量更新支持算法参数（`testcasesApi.batchAction('update_algorithm_params', ids, payload)` 对应后端批量接口）
- [x] 算法关联评估维度接口（`GET /api/v1/algorithm/dimensions/:type`，AlgorithmDimensionRelation）

### 11.2 前端实施

- [x] 组件化为 `TestCaseModal/` 目录（index.vue + CaseForm.vue + RoundConfigEditor.vue + OverallEvaluationEditor.vue + useDimensionConfig.ts + types.ts）
- [x] 集成 AlgorithmSelector 组件（components/common/AlgorithmSelector.vue，单选模式）
- [x] 按轮参数编辑：RoundConfigEditor 接收 caseAlgorithmParams/algorithmFormSchema/algorithmParams，写回 algorithm_params 独立列
- [x] 维度按算法过滤：useDimensions.fetchDimensionsByAlgorithmType + useDimensionConfig
- [x] 保存编排：testCaseStore（Application 层）+ testcasesApi（Infrastructure 层），保存前归一化 camelCase
- [x] 参考参数路径：sections/ReferencePathStep.vue（reference_params 独立列）
- [x] 编辑回填：独立列兼容读取（algorithmParams || algorithm_params）+ 首轮参数作为 AlgorithmSelector 初始值

### 11.3 测试验证

- [x] 新建用例 - 选择算法类型
- [x] 新建用例 - 按轮填写动态参数（写入独立列）
- [x] 新建用例 - 保存验证（algorithm_params 独立提交）
- [x] 编辑用例 - 加载数据（独立列回填 + 首轮参数回显）
- [x] 编辑用例 - 修改算法类型（schema/关联维度联动刷新）
- [x] 编辑用例 - 更新参数（按轮独立列更新）
- [x] 复制用例 - 算法参数复制
- [x] 不同算法类型切换测试
