# 10_RoundConfigEditor 轮次配置编辑器

> 重构组件：`frontend/src/components/common/test-case/TestCaseModal/RoundConfigEditor.vue`

## 功能说明

轮次配置编辑器是 CaseForm 的**核心区域**。

**核心设计原则：参数驱动，不硬编码字段**

每轮表单中"有哪些字段可填"由第1步 `AlgorithmConfigPage` 中的 `case_algorithm_params` 表定义驱动，通过 DynamicForm 动态渲染。RoundConfigEditor 自身不硬编码任何算法相关的配置字段（如导轨距离、音量、声纹、干扰人等）。

- **通用组件**：所有算法均可使用，表单内容由 `case_algorithm_params` 定义决定
- **单轮算法**：默认 1 轮，可手动添加
- **多轮算法**：任意轮次
- **复制机制**：添加新轮次时可复制整轮或选择复制部分

### 每轮区域划分

| 区域 | 数据来源 | 渲染方式 |
|------|---------|---------|
| 本轮输入 | `algorithm_api_params` (direction=input) | 遍历 input 参数定义渲染 |
| 音频配置 | 用户选择（结构性） | AudioConfigList 组件 |
| 背景噪声 | 用户选择（结构性，E2E） | BackgroundNoiseEditor |
| **所有算法参数** | `case_algorithm_params` 表 | **DynamicForm** |
| 评估维度 | 用户选择（结构性） | RoundEvaluationEditor |
| 参考字段 | 系统自动生成 | 只读展示 |

> **输入方式**：不再是互斥单选（`inputType: 'text' | 'audio'`）。
> 单轮支持多种输入共存——由 `algorithm_api_params` 中 direction=input 的参数定义决定。
> voice_llm 同时注册了 `input_text(text)` 和 `input_audio(audio_file)` 两个输入参数，
> 两个字段同时显示，用户可只填文本、只填音频、或两者都填。

## Props / Events

```ts
interface Props {
  modelValue: RoundConfigItem[]     // 轮次配置列表
  testType: 'api' | 'e2e'           // 测试类型（传给 DynamicForm 做 scope 过滤）
  caseAlgorithmParams: any[]        // 当前算法的 case_algorithm_params 定义列表
  apiInputParams?: any[]            // algorithm_api_params (direction=input) 列表
}

interface Emits {
  'update:modelValue'(value: RoundConfigItem[])
}
```

### caseAlgorithmParams 来源

```
第1步 AlgorithmConfigPage
  └─ case_algorithm_params 表
       └─ GET /algorithm/case-params?algorithm_type=voice_llm&scope={testType}
            └─ 返回本算法的所有用例参数定义
                 └─ 传入 RoundConfigEditor → DynamicForm 渲染
```

### apiInputParams 来源

```
第1步 AlgorithmConfigPage
  └─ algorithm_api_params 表
       └─ GET /algorithm/api-params?algorithm_type=voice_llm&direction=input
            └─ 返回本算法的 API 输入字段定义
                 └─ 传入 RoundConfigEditor → 渲染输入区域
```

## 显示条件

**所有用例均显示**（通用能力，不绑定算法类型）：

```ts
// 在 CaseForm 中始终渲染
<RoundConfigEditor
  v-model="formData.config.rounds"
  :test-type="testType"
  :case-algorithm-params="caseAlgorithmParams"
  :api-input-params="apiInputParams"
/>
```

## 组件结构

```vue
<template>
  <div class="round-config-editor">
    <div class="editor-header">
      <h4>轮次配置</h4>
      <el-button type="primary" @click="addRound">+ 添加轮次</el-button>
    </div>

    <draggable v-model="rounds" item-key="roundNumber" @end="renumber">
      <template #item="{ element: round, index }">
        <el-card class="round-card">
          <template #header>
            <div class="round-header">
              <span>第 {{ round.roundNumber }} 轮</span>
              <el-button-group>
                <el-button size="small" @click="copyRound(index)">复制</el-button>
                <el-button size="small" @click="removeRound(index)" type="danger"
                           :disabled="rounds.length === 1">删除</el-button>
              </el-button-group>
            </div>
          </template>

          <!-- ===== 输入区域（由 algorithm_api_params 驱动，多种输入共存） ===== -->

          <!--
            遍历 apiInputParams (direction=input)，每个参数独立渲染。
            voice_llm 注册了 input_text(text) 和 input_audio(audio_file)，
            因此两个字段同时显示，用户可填一个或两个都填。

            旧设计：inputType 互斥单选 → 只能选一种输入方式
            新设计：每种输入类型独立字段 → 多种输入共存

            值写入 round.algorithmParams 数组：
            {field_code: param.param_code, field_value: 用户输入值}
          -->
          <div class="section-block">
            <h5>本轮输入</h5>
            <template v-for="param in apiInputParams" :key="param.param_code">
              <el-form-item v-if="param.param_type === 'text'" :label="param.param_name">
                <el-input
                  :model-value="getAlgoParamValue(round.algorithmParams, param.param_code)"
                  @update:model-value="setAlgoParamValue(round, param.param_code, $event)"
                  :placeholder="param.help_text || `输入${param.param_name}`"
                  type="textarea" :rows="2"
                />
              </el-form-item>

              <el-form-item v-else-if="param.param_type === 'audio_file'" :label="param.param_name">
                <AudioSelect
                  :model-value="getAlgoParamValue(round.algorithmParams, param.param_code)"
                  @update:model-value="setAlgoParamValue(round, param.param_code, $event)"
                  :label="param.param_name"
                />
              </el-form-item>
            </template>
          </div>

          <!-- ===== 结构性区域（非算法驱动） ===== -->

          <div class="section-block">
            <h5>音频配置</h5>
            <AudioConfigList v-model="round.audios" :test-type="testType" />
          </div>

          <div v-if="testType === 'e2e'" class="section-block">
            <h5>背景噪声</h5>
            <BackgroundNoiseEditor v-model="round.backgroundNoise" />
          </div>

          <!-- ===== 算法驱动区域（核心：由 case_algorithm_params 定义） ===== -->

          <!--
            DynamicForm 根据 case_algorithm_params 定义动态渲染所有表单字段。
            不硬编码任何 E2E/API 条件判断——字段的显隐、类型、默认值
            全部由第1步 AlgorithmConfigPage 的参数定义决定。

            DynamicForm 内部：
            - 按 scope 过滤：只显示 scope='common' 或 scope 匹配 testType 的参数
            - 按 param_type 渲染：slider → el-slider, switch → el-switch, 等
            - 复杂类型用子编辑器：noise_config → BackgroundNoiseEditor 等

            所有参数值统一写入 round.algorithmParams 数组
          -->
          <div class="section-block">
            <h5>算法参数</h5>
            <DynamicForm
              v-model="round.algorithmParams"
              :params="filteredCaseParams"
              :scope="testType"
            />
          </div>

          <!-- ===== 评估（结构性） ===== -->
          <RoundEvaluationEditor v-model="round.evaluation" />

          <!-- ===== 参考字段（系统自动生成，只读） ===== -->
          <el-collapse v-if="round.referenceParamsPath">
            <el-collapse-item title="参考字段（自动生成）">
              <p class="ref-path-display">{{ round.referenceParamsPath }}</p>
            </el-collapse-item>
          </el-collapse>

        </el-card>
      </template>
    </draggable>

    <CopyRoundDialog v-model:visible="copyDialogVisible"
      :source-round="copySource" @confirm="handleCopyConfirm" />
  </div>
</template>
```

### algorithmParams 读写辅助函数

```ts
function getAlgoParamValue(params: AlgorithmParamItem[], fieldCode: string): any {
  const item = params?.find(p => p.field_code === fieldCode)
  return item?.field_value
}

function setAlgoParamValue(round: RoundConfigItem, fieldCode: string, value: any) {
  const params = round.algorithmParams ?? []
  const idx = params.findIndex(p => p.field_code === fieldCode)
  if (idx >= 0) {
    params[idx] = { field_code: fieldCode, field_value: value }
  } else {
    params.push({ field_code: fieldCode, field_value: value })
  }
  round.algorithmParams = [...params]
}
```

### DynamicForm 的 param_type 与组件映射

`DynamicForm` 内部根据 `case_algorithm_params.param_type` 渲染不同组件：

| param_type | 渲染组件 | 示例 field_code |
|-----------|---------|----------------|
| `slider` | el-slider | railDistance, volumeLevel |
| `switch` | el-switch | voiceprintEnabled |
| `number` | el-input-number | voiceprintWaitTime, waitTime |
| `audio_select` | AudioSelectButton | voiceprintAudioId, promptAudioId |
| `device_select` | DeviceSelect | （设备选择） |
| `noise_config` | BackgroundNoiseEditor | backgroundNoise |
| `interferer_list` | InterfererConfigEditor | interferers |
| `select` | el-select | （选项类参数） |
| `text` | el-input | （文本类参数） |

> 标准 param_type（slider/switch/number/select/text）由 DynamicForm 内置渲染。
> 复杂 param_type（audio_select/noise_config/interferer_list）需要 DynamicForm 注册子编辑器组件。

### scope 过滤

DynamicForm 内部按 scope 过滤参数可见性（已在 `15_DynamicForm_scope过滤.md` 中定义）：

```ts
const filteredCaseParams = computed(() => {
  return props.caseAlgorithmParams.filter(param => {
    return param.scope === 'common' || param.scope === props.testType;
  });
});
```

## 复制轮次机制

### 添加新轮次

```ts
function addRound() {
  if (rounds.value.length === 0) {
    emit('update:modelValue', [createEmptyRound(1)])
    return
  }
  copyDialogVisible.value = true
  copySource.value = rounds.value[rounds.value.length - 1]
}

function createEmptyRound(number: number): RoundConfigItem {
  // 从 case_algorithm_params 定义中提取默认值，构造 [{field_code, field_value}] 数组
  const defaultParams: AlgorithmParamItem[] = []
  for (const param of props.caseAlgorithmParams) {
    if (param.default_value !== undefined && param.default_value !== null) {
      defaultParams.push({ field_code: param.param_code, field_value: param.default_value })
    }
  }

  return {
    roundNumber: number,
    algorithmParams: defaultParams,
  }
}
```

### 复制选项

用户可选择复制哪些配置区域到新的轮次：

```vue
<!-- CopyRoundDialog.vue -->
<el-checkbox-group v-model="selectedSections">
  <el-checkbox label="audios">音频配置</el-checkbox>
  <!-- 以下由 case_algorithm_params 驱动，不再硬编码具体参数名 -->
  <el-checkbox label="algorithmParams">算法参数</el-checkbox>
  <el-checkbox label="evaluation">评估维度</el-checkbox>
</el-checkbox-group>
```

### 复制逻辑

```ts
function handleCopyAll() {
  const newRound = deepClone(copySource.value)
  newRound.roundNumber = rounds.value.length + 1
  delete newRound.referenceParamsPath   // 不复制（由系统生成）
  emit('update:modelValue', [...rounds.value, newRound])
  visible.value = false
}

function handleCopySelected() {
  const newRound = createEmptyRound(rounds.value.length + 1)
  const source = copySource.value

  for (const section of selectedSections.value) {
    switch (section) {
      case 'audios':           newRound.audios = deepClone(source.audios); break
      case 'algorithmParams':  newRound.algorithmParams = deepClone(source.algorithmParams); break
      case 'evaluation':       newRound.evaluation = deepClone(source.evaluation); break
    }
  }

  emit('update:modelValue', [...rounds.value, newRound])
  visible.value = false
}

function handleBlankRound() {
  emit('update:modelValue', [...rounds.value, createEmptyRound(rounds.value.length + 1)])
  visible.value = false
}
```

## 删除/排序

```ts
function removeRound(index: number) {
  const updated = rounds.value.filter((_, i) => i !== index)
    .map((r, i) => ({ ...r, roundNumber: i + 1 }))
  emit('update:modelValue', updated)
}

onMounted(() => {
  if (!props.modelValue || props.modelValue.length === 0) {
    emit('update:modelValue', [createEmptyRound(1)])
  }
})
```

## 旧设计 vs 新设计对比

| 方面 | 旧设计 | 新设计 |
|------|--------|--------|
| 输入类型 | `inputType` 互斥单选 | `algorithm_api_params` 驱动，多种共存 |
| E2E 字段 | `v-if="mode === 'e2e'"` 硬编码 | `case_algorithm_params` + DynamicForm |
| 新增参数 | 改组件代码 | 改数据库种子数据（case_algorithm_params INSERT） |
| 参数存储 | 分散到 RoundConfigItem 各字段 | 统一存入 `round.algorithmParams[{field_code, field_value}]` |
| waitTime | 轮次顶层 `round.waitTime` | `algorithmParams[{field_code:'waitTime', ...}]` |

## 引用关系

- ← `01_选算法/backend/02_CaseAlgorithmParam_scope字段` — scope 过滤机制
- ← `01_选算法/frontend/15_DynamicForm_scope过滤` — DynamicForm 过滤实现
- ← `01_选算法/backend/07_voice_llm算法参数种子数据` — 参数定义来源
- ← `01_选算法/backend/08_field_mapper_voice_llm映射` — algorithm_api_params 输入定义
- ← `02_选用例/frontend/01_types.ts新接口定义` — RoundConfigItem 接口
- ← `02_选用例/frontend/06_CaseForm_test_type驱动` — 在 CaseForm 中挂载
- → `02_选用例/frontend/12_VoiceprintConfigEditor` — DynamicForm 子编辑器（param_type=voiceprint_editor）
- → `02_选用例/frontend/13_InterfererConfigEditor` — DynamicForm 子编辑器（param_type=interferer_list）
- → `02_选用例/frontend/14_RoundEvaluationEditor` — 评估维度子组件
