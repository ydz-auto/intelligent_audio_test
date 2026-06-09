# 06_CaseForm test_type 驱动（参数驱动版）

> 文件：`frontend/src/components/common/test-case/TestCaseModal/CaseForm.vue`

## 现状分析

CaseForm 是用例编辑表单的核心组件。双记录迁移后，用例级别已有 test_type。

## 改造方案（参数驱动）

CaseForm 负责加载当前算法的参数定义，传给 RoundConfigEditor，由 DynamicForm 动态渲染。

### 1. 用例级别 test_type 驱动

```ts
const props = defineProps<{
  formData: Partial<TestCaseFormData>
  testCaseGroups: string[]
  audioConfig?: any
  testType: 'api' | 'e2e'
}>()

const isAPI = computed(() => props.testType === 'api')
const isE2E = computed(() => props.testType === 'e2e')
```

### 2. 加载算法参数定义

当 `algorithmType` 变化时，从后端加载参数定义：

```ts
// 当前算法的用例参数定义（来自 case_algorithm_params 表）
const caseAlgorithmParams = ref<any[]>([])

// 当前算法的 API 输入字段定义（来自 algorithm_api_params 表，direction=input）
const apiInputParams = ref<any[]>([])

// 监听 algorithmType 变化，加载参数定义
watch(() => props.formData.algorithmType, async (newType) => {
  if (!newType) {
    caseAlgorithmParams.value = []
    apiInputParams.value = []
    return
  }
  
  // 加载用例参数定义（case_algorithm_params 表）
  caseAlgorithmParams.value = await algorithmApi.getCaseParams({
    algorithm_type: newType,
    scope: props.testType   // 按 test_type 过滤 scope
  })
  
  // 加载 API 输入字段定义（algorithm_api_params 表，direction=input）
  apiInputParams.value = await algorithmApi.getApiParams({
    algorithm_type: newType,
    direction: 'input'
  })
}, { immediate: true })
```

### 3. CaseForm 整体结构

```vue
<template>
  <div class="case-form">
    <!-- 区域 1：基本信息 -->
    <el-card class="basic-info">
      <template #header><span>基本信息</span></template>
      <el-form-item label="用例名称">...</el-form-item>
      <el-form-item label="描述">...</el-form-item>
      <el-form-item label="分组">...</el-form-item>
      <el-form-item label="标签">...</el-form-item>
      <el-form-item label="测试类型">
        <el-tag :type="testType === 'api' ? 'success' : 'warning'">
          {{ testType === 'api' ? 'API 测试' : 'E2E 测试' }}
        </el-tag>
        <el-link v-if="formData.related_case_id" @click="openRelatedCase">
          查看关联{{ testType === 'api' ? 'E2E' : 'API' }}用例
        </el-link>
      </el-form-item>
    </el-card>

    <!-- 区域 2：算法选择 -->
    <AlgorithmSelector v-model="formData.algorithmType" />

    <!-- 区域 3：轮次编辑器（核心区域，接收参数定义） -->
    <RoundConfigEditor
      v-model="formData.config.rounds"
      :test-type="testType"
      :case-algorithm-params="caseAlgorithmParams"
      :api-input-params="apiInputParams"
    />
  </div>
</template>
```

> **注意**：
> - 评测维度已下沉到每轮的 `evaluation.dimensions` 中
> - 独立的 DynamicForm 不再出现在 CaseForm 顶层（所有参数由 RoundConfigEditor 内的 DynamicForm 渲染）

### 4. 数据流

```
用户选择 algorithmType
  │
  ├─ GET /algorithm/case-params?algorithm_type=voice_llm&scope=e2e
  │    └─ 返回 case_algorithm_params（导轨/音量/声纹/噪声/干扰人/打断...）
  │         └─ 传入 RoundConfigEditor → DynamicForm 渲染表单
  │
  ├─ GET /algorithm/api-params?algorithm_type=voice_llm&direction=input
  │    └─ 返回 algorithm_api_params input 字段（input_text/input_audio）
  │         └─ 传入 RoundConfigEditor → 渲染输入区域
  │
  └─ 用户填写值 → 存入 round.algorithmParams[param_code]
```

## 不变部分

- 用例基本信息区域
- 算法选择（AlgorithmSelector）
- 表单校验逻辑（需补充 test_type 相关校验）

## 废弃部分

- 独立的评测维度区域 → 移入每轮 `round.evaluation.dimensions`
- 独立的音频配置区域 → 移入每轮 `round.audios`
- 独立的 DynamicForm（CaseForm 顶层）→ DynamicForm 下沉到 RoundConfigEditor 内部
- 独立的背景噪声/设备环境/声纹/干扰人区域 → 全部由 DynamicForm 根据 case_algorithm_params 动态渲染

## 引用关系

- ← `01_选算法/backend/02_CaseAlgorithmParam_scope字段` — scope 过滤
- ← `01_选算法/backend/07_voice_llm算法参数种子数据` — 参数定义来源
- ← `02_选用例/frontend/01_types.ts新接口定义`
- ← `02_选用例/frontend/05_AddTestCaseModal_test_type选择`
- → `02_选用例/frontend/10_RoundConfigEditor` — 接收参数定义，DynamicForm 驱动
- → `02_选用例/frontend/12_VoiceprintConfigEditor` — DynamicForm 子编辑器
- → `02_选用例/frontend/13_InterfererConfigEditor` — DynamicForm 子编辑器
- → `02_选用例/frontend/14_RoundEvaluationEditor` — 评估维度子组件
