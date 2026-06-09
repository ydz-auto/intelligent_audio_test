# 16_APITest 页面适配

> 文件：`frontend/src/views/APITest.vue` + `frontend/src/views/APITestLogic/apiTest.ts`

## 现状分析

APITest.vue 是 API 测试的 5 步向导页面：

```
选算法 → 选用例 → 选被测API → 执行测试 → 查看结果
```

### 现有用例筛选逻辑

`apiTest.ts` 中通过 `useApiTest.ts` composable 过滤用例：

```ts
// useApiTest.ts 中的过滤逻辑
function isApiTestCase(caseItem: TestCase): boolean {
  // 检查 config.type === 'api' 或 type === 'api' 或存在 config.apiAudio
  return config.type === 'api' || type === 'api' || !!config.apiAudio
}
```

当前通过**音频级别的 testType** 推断用例类型，而非用例级别的 `test_type` 字段。

### 现有 API 选择逻辑

```ts
// apiTest.ts 中的 API 筛选
const allFilteredAPIs = computed(() =>
  allAPIs.value.filter(api =>
    api.algorithmType === selectedAlgorithmType.value &&
    (apiFilter.value === 'all' || api.status === apiFilter.value) &&
    matchesSearch(api, apiSearchQuery.value)
  )
)
```

## 改造方案

### 1. 用例筛选改为使用 test_type 字段

```ts
// useApiTest.ts 改造
function isApiTestCase(caseItem: TestCase): boolean {
  // 优先使用用例级别的 test_type
  if (caseItem.test_type) {
    return caseItem.test_type === 'api'
  }
  // 降级到音频级别推断（向后兼容）
  const config = caseItem.config
  return config?.type === 'api' || !!config?.apiAudio
}
```

### 2. voice_llm 算法自动发现

当用户选择 voice_llm 算法时，自动启用多轮会话相关 UI 提示：

```ts
// apiTest.ts
const isVoiceLLM = computed(() => selectedAlgorithmType.value === 'voice_llm')

// 在步骤2（选用例）显示提示
const stepHints = computed(() => ({
  1: isVoiceLLM.value
    ? 'voice_llm 用例支持多轮对话，每个用例可配置多个轮次的输入文本/音频'
    : ''
}))
```

### 3. API 选择页面不变

voice_llm 的 API 选择逻辑与现有算法一致：
- 按 `algorithmType` 过滤 API 列表
- 仅允许选择在线的 API
- 支持搜索和分页

无需额外改造。

### 4. 任务创建适配

```ts
// apiTest.ts 任务创建
async function handleStartTask() {
  const payload = {
    name: taskName.value,
    type: 'api',
    algorithmType: selectedAlgorithmType.value,
    caseIds: selectedTestCaseIds.value,
    apiIds: selectedAPIIds.value,
    tags: selectedTags.value
  }
  // voice_llm 和其他算法使用相同的任务创建 API
  const task = await tasksApi.create(payload)
  await tasksApi.start(task.id)
}
```

### 5. 确认：5 步流程不需要改动

APITest.vue 的 5 步向导结构完全不变：

| 步骤 | 组件 | 改动 |
|------|------|------|
| 0 | AlgorithmSelectionPanel | 不变 |
| 1 | TestCaseListContainer | 不变（筛选逻辑在 composable 中） |
| 2 | ResourceSelectionGrid | 不变 |
| 3 | TestExecutionComponent | 不变（多轮进度在执行器文档中） |
| 4 | TaskReportPanel | 不变 |

## 不变部分

- APITest.vue 的 5 步向导结构
- ResourceSelectionGrid 组件
- API 筛选逻辑（按 algorithmType）
- 任务创建/启动/停止控制
- 进度显示基础组件

## 引用关系

- ← `02_选用例/backend/01_TestCase模型新增字段` — TestCase.test_type
- ← `02_选用例/frontend/07_testCaseStore_test_type处理` — Store 提供含 test_type 的用例
- → `04_执行测试/backend/12_api_executor多轮会话主循环` — 后端执行 voice_llm
