# 05_AddTestCaseModal test_type 选择

> 文件：`frontend/src/components/common/test-case/AddTestCaseModal.vue`

## 现状分析

AddTestCaseModal 是一个简单的多选模态窗，用于从已有用例中选取用例添加到分组。当前组件完全不感知 test_type：

```ts
// Props
{ visible: Boolean, testCases: Array }

// Emits
['close', 'add-test-cases']

// 仅支持文本搜索和标签筛选
data() {
  return { searchQuery: '', selectedTag: 'all', selectedTestCases: [] }
}
```

## 改造方案

### 1. 新建用例时选择 test_type

当 AddTestCaseModal 承担"新建用例"入口时（与"选取已有用例"共存），新增 test_type 选择步骤：

```vue
<template>
  <el-dialog>
    <!-- 模式一：选取已有用例（现有功能） -->
    <div v-if="mode === 'select'">
      <!-- 新增 test_type 筛选下拉 -->
      <el-select v-model="testTypeFilter" placeholder="测试类型" clearable>
        <el-option label="全部" value="all" />
        <el-option label="API" value="api" />
        <el-option label="E2E" value="e2e" />
      </el-select>
      <!-- 现有序列 -->
    </div>

    <!-- 模式二：新建空用例 -->
    <div v-if="mode === 'create'">
      <el-radio-group v-model="newTestType">
        <el-radio-button value="api">API 测试</el-radio-button>
        <el-radio-button value="e2e">E2E 测试</el-radio-button>
      </el-radio-group>
    </div>
  </el-dialog>
</template>
```

### 2. 选取已有用例时按 test_type 筛选

```ts
const filteredTestCases = computed(() => {
  let result = props.testCases
  // test_type 筛选
  if (testTypeFilter.value !== 'all') {
    result = result.filter(tc => tc.test_type === testTypeFilter.value)
  }
  // 现有搜索和标签筛选...
  return result
})
```

### 3. test_type 创建后不可变

新建用例时选定的 test_type 传递给 CaseForm，后续编辑中不可修改：

```ts
const handleCreateNew = () => {
  emit('add-test-cases', {
    mode: 'create',
    test_type: newTestType.value
  })
}
```

## 不变部分

- 文本搜索逻辑
- 标签筛选
- 多选勾选逻辑
- 批量添加确认

## 引用关系

- ← `02_选用例/frontend/04_TestCaseListContainer_test_type` — 传递 test_type 参数
- → `02_选用例/frontend/06_CaseForm_test_type驱动` — 新建用例时的 test_type
