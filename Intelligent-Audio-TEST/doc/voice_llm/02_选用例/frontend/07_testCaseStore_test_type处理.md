# 07_testCaseStore test_type 处理

> 文件：`frontend/src/store/testCaseStore.ts`

## 现状分析

testCaseStore（896行）是基于 Pinia 的用例状态管理，提供 CRUD、批量操作、分组管理等功能。

### 当前 test_type 处理

Store 本身不直接处理 `test_type`，依赖后端返回的 `TestCase` 对象中的 `config` 结构隐式区分。关键状态和方法：

```ts
// 状态
const testCases = ref<TestCase[]>([])

// CRUD
addTestCase(data)      // POST /api/v1/testcases
updateTestCase(id, data) // PUT /api/v1/testcases/{id}
deleteTestCase(id)       // DELETE /api/v1/testcases/{id}
copyTestCase(id)         // POST /api/v1/testcases/{id}/copy

// 批量操作
batchUpdateDimensions(selectedCases, dimensions) // 按 config.dimensions.api/e2e 区分
```

## 改造方案

### 1. 用例列表按 test_type 过滤

新增按 test_type 获取用例列表的筛选方法：

```ts
// 新增筛选参数
const currentTestTypeFilter = ref<'all' | 'api' | 'e2e'>('all')

// fetchCasesByGroup 增加 test_type 过滤参数
async function fetchCasesByGroup(groupName: string, options?: {
  test_type?: 'api' | 'e2e'
}) {
  const params: Record<string, any> = {
    group: groupName,
    page: 1,
    per_page: DEFAULT_FETCH_PAGE_SIZE,
  }
  if (options?.test_type) {
    params.test_type = options.test_type
  }
  const response = await testcasesApi.getByGroup(params)
  // ...
}
```

### 2. CRUD 操作传递 test_type

```ts
// 创建用例
async function addTestCase(data: TestCaseFormData) {
  const payload = {
    ...data,
    test_type: data.test_type            // 传递 test_type
  }
  const response = await testcasesApi.create(payload)
  upsertTestCaseLocal(response.data)
  return response.data
}

// 更新用例（test_type 不可变，不传递）
async function updateTestCase(id: string | number, data: Partial<TestCaseFormData>) {
  const { test_type, ...payload } = data  // 排除 test_type
  const response = await testcasesApi.update(id, payload)
  upsertTestCaseLocal(response.data)
  return response.data
}

// 删除用例
async function deleteTestCase(id: string | number) {
  await testcasesApi.delete(id)
  removeTestCaseLocal(id)
}

// 复制用例
async function copyTestCase(id: string | number) {
  const response = await testcasesApi.copy(id)
  // 复制会生成新的 test_type
  upsertTestCaseLocal(response.data)
  return response.data
}
```

### 3. 批量操作适配

批量更新维度时不再区分 `api`/`e2e`，因为每条用例已有确定的 `test_type`：

```ts
// 改造后
async function batchUpdateDimensions(selectedCases: string[], dimensions: DimensionConfig[]) {
  // 不再按 {api, e2e} 区分
  await testcasesApi.batchUpdate({
    ids: selectedCases,
    config: { dimensions }
  })
  // 本地更新...
}
```

### 4. 分组统计

分组统计增加 test_type 分布：

```ts
interface GroupStat {
  name: string
  total: number
  api: number
  e2e: number
}
```

## 不变部分

- Store 整体架构（defineStore + setup 模式）
- 分组 CRUD（addGroup/updateGroup/deleteGroup）
- 导入功能
- 标签管理（batchAddTags/batchRemoveTags/batchRenameTag）
- 错误处理（handleError）
- 本地状态操作（upsertTestCaseLocal/removeTestCaseLocal）

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — TestCaseFormData 含 test_type
- ← `02_选用例/backend/05_testcase_controller双记录CRUD` — 后端双记录 API
- → `02_选用例/frontend/04_TestCaseListContainer_test_type` — 列表组件消费 Store
