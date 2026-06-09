# 04_TestCaseListContainer test_type 适配

> 文件：`frontend/src/components/common/test-case/TestCaseListContainer.vue`

## 现状分析

TestCaseListContainer 是用例列表容器组件，提供分组展示、筛选、排序等功能。

### 现有 test_type 处理

```ts
// 本地 filter ref
const testTypeFilter = ref<'all' | 'api' | 'e2e'>('all')

// filteredTestCases 计算属性（446-535行）中的筛选逻辑：
if (testTypeFilter.value !== 'all') {
  // 1. 检查 testCase.type 或 config.type
  // 2. 降级到 normalizeTestCaseConfig(config) 检查 apiAudios/dryAudios
}
```

当前筛选逻辑依赖音频级别的 `testType` 推断用例类型，没有用例级别的 `test_type` 字段。

### Props

```ts
{
  testCaseGroups?: Record<string, TestCase[]>
  tags?: string[]
  paginationInfo?: PaginationInfo
  isLoading?: boolean
  algorithmTypeFilter?: string
}
```

### Emits

```ts
{
  deleteGroup, deleteTestCase, openAddModal, openEditModal,
  openCreateGroupModal, openEditGroupModal, openImportModal,
  openExportModal, updateSelectedCases
}
```

## 改造方案

### 1. 筛选逻辑改为使用 test_type 字段

```ts
// 改造后的筛选逻辑
const filteredTestCases = computed(() => {
  // ...现有过滤...

  // test_type 筛选（简化）
  if (testTypeFilter.value !== 'all') {
    result = result.filter(tc => tc.test_type === testTypeFilter.value)
  }

  return result
})
```

### 2. 列表新增 test_type 列

```vue
<el-table-column label="测试类型" width="100">
  <template #default="{ row }">
    <el-tag
      :type="row.test_type === 'api' ? 'success' : 'warning'"
      size="small"
    >
      {{ row.test_type === 'api' ? 'API' : 'E2E' }}
    </el-tag>
  </template>
</el-table-column>
```

### 3. 关联用例快捷跳转

当用例有 `related_case_id` 时，显示"查看关联用例"链接：

```vue
<el-table-column label="关联用例" width="120">
  <template #default="{ row }">
    <el-link
      v-if="row.related_case_id"
      type="primary"
      @click="navigateToRelatedCase(row.related_case_id)"
    >
      {{ getRelatedCaseName(row.related_case_id) }}
    </el-link>
    <span v-else class="text-gray-400">—</span>
  </template>
</el-table-column>
```

### 4. GroupStat 展示

分组统计信息中增加 API/E2E 数量：

```vue
<!-- 分组卡片统计 -->
<div class="group-stats">
  共 {{ stat.total }} 个用例
  (API: {{ stat.api }}, E2E: {{ stat.e2e }})
</div>
```

### 5. 创建用例时传递 test_type

`openAddModal` emit 增加 `test_type` 参数，让新建用例时预选测试类型：

```ts
// 在筛选器有 testTypeFilter 时，传递给新建模态窗
const handleAddCase = (group?: string) => {
  emit('openAddModal', group, {
    algorithmType: algorithmTypeFilter.value,
    test_type: testTypeFilter.value !== 'all' ? testTypeFilter.value : undefined
  })
}
```

## 不变部分

- 分组展示逻辑
- 拖拽排序
- 批量操作（选择、删除、移动）
- 分页加载更多
- 音频预览功能

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — TestCase 接口含 test_type
- ← `02_选用例/frontend/07_testCaseStore_test_type处理` — Store 提供含 test_type 的用例列表
- → `02_选用例/frontend/05_AddTestCaseModal_test_type选择` — 新建用例选择 test_type
