# E2ETest/APITest 算法配置管理模态窗打开异常修复

## 问题描述

在 E2ETest (`/#/E2ETest`) 和 APITest (`/#/APITest`) 页面，点击算法卡片上的齿轮图标（算法配置）时，未能正确打开算法参数 CRUD 模态窗（`AlgorithmConfigModal`）。

## 影响范围

- **E2ETest 页面**：点击齿轮图标后模态窗无法以正确的 `edit` 模式打开，`algorithmModalMode` 和 `algorithmEditData` 未被传递
- **APITest 页面**：点击齿轮图标后模态窗以 `edit` 模式打开，但 `editData` 使用的是简略的 `AlgorithmOption` 对象而非完整的算法定义数据，且 API 端点错误

## 根因分析

### 1. `useAlgorithmSelection.ts` — `openAlgorithmConfigModal` 函数缺陷

**文件**: `frontend/src/composables/useAlgorithmSelection.ts` (第86-100行)

- **API 端点错误**: 请求 `/api/v1/algorithm/${algo.value}` 而非 `/api/v1/algorithm/definitions/${algo.value}`，导致获取算法详情失败
- **未设置 `algorithmModalMode`**: 函数只设置了 `editingAlgorithm`，没有同步设置 `algorithmModalMode` 和 `algorithmEditData`，导致 `AlgorithmConfigModal` 无法感知应进入 `edit` 模式
- **参数不可选**: `algo` 参数为必填，无法支持以 `list` 模式打开模态窗

### 2. `useE2eView.ts` — 状态未透传

**文件**: `frontend/src/composables/useE2eView.ts`

- 从 `useAlgorithmSelection` 解构时**遗漏** `algorithmModalMode` 和 `algorithmEditData`
- return 语句中**未导出**这两个值
- 解构了 `useAlgorithmSelection` 中**不存在**的 `openEditAlgorithmModal`，导致运行时为 `undefined`

### 3. `apiTest.ts` — 状态未透传

**文件**: `frontend/src/views/APITestLogic/apiTest.ts`

- 从 `useAlgorithmSelection` 解构时**遗漏** `algorithmModalMode` 和 `algorithmEditData`
- return 语句中**未导出**这两个值

### 4. `APITest.vue` — 内联表达式绕过状态管理

**文件**: `frontend/src/views/APITest.vue` (第258-259行)

```vue
:mode="editingAlgorithm ? 'edit' : 'list'"
:edit-data="editingAlgorithm"
```

- 使用内联表达式计算 mode，而非使用 `algorithmModalMode` 状态变量
- `editingAlgorithm` 是 `AlgorithmOption` 类型（仅含 `value/name/group_id/group_name`），缺少完整的参数、映射等配置数据，传给 `AlgorithmConfigModal` 作为 `editData` 时字段不完整

### 5. `E2ETest.vue` — 解构不存在的值

**文件**: `frontend/src/views/E2ETest.vue` (第388行)

- 从 `useE2eView()` 解构了不存在的 `openEditAlgorithmModal`

## 修复方案

### 修复1: `useAlgorithmSelection.ts` — 修正 `openAlgorithmConfigModal`

```typescript
// 修复前
async function openAlgorithmConfigModal(algo: AlgorithmOption) {
  try {
    const response = await fetch(`/api/v1/algorithm/${algo.value}`)
    // ...
    editingAlgorithm.value = result.data
  } catch (error) { ... }
  algorithmModalVisible.value = true
}

// 修复后
async function openAlgorithmConfigModal(algo?: AlgorithmOption) {
  if (algo) {
    try {
      const response = await fetch(`/api/v1/algorithm/definitions/${algo.value}`)
      const result = await response.json()
      if (result.success && result.data) {
        editingAlgorithm.value = result.data
        algorithmEditData.value = result.data
      } else {
        editingAlgorithm.value = algo
        algorithmEditData.value = algo as any
      }
    } catch (error) {
      editingAlgorithm.value = algo
      algorithmEditData.value = algo as any
    }
    algorithmModalMode.value = 'edit'
  } else {
    algorithmModalMode.value = 'list'
    algorithmEditData.value = null
    editingAlgorithm.value = null
  }
  algorithmModalVisible.value = true
}
```

变更要点:
- API 端点修正为 `/api/v1/algorithm/definitions/${algo.value}`
- 同步设置 `algorithmModalMode` 和 `algorithmEditData`
- `algo` 参数改为可选，支持以 `list` 模式打开

### 修复2: `useE2eView.ts` — 补充解构和导出

```typescript
// 解构补充
const {
  // ... 原有值
  algorithmModalMode,       // 新增
  algorithmEditData,        // 新增
  openCreateAlgorithmModal, // 新增
  // openEditAlgorithmModal, // 移除（不存在）
  // ...
} = useAlgorithmSelection({ ... })

// return 补充
return {
  // ...
  algorithmModalMode,       // 新增
  algorithmEditData,        // 新增
  openCreateAlgorithmModal, // 新增
  // ...
}
```

### 修复3: `apiTest.ts` — 补充解构和导出

```typescript
// 解构补充
const {
  // ... 原有值
  algorithmModalMode,  // 新增
  algorithmEditData,   // 新增
  // ...
} = useAlgorithmSelection({ ... })

// return 补充
return {
  // ...
  algorithmModalMode,  // 新增
  algorithmEditData,   // 新增
  // ...
}
```

### 修复4: `APITest.vue` — 使用状态变量替代内联表达式

```vue
<!-- 修复前 -->
<AlgorithmConfigModal
  v-model:visible="algorithmModalVisible"
  :mode="editingAlgorithm ? 'edit' : 'list'"
  :edit-data="editingAlgorithm"
/>

<!-- 修复后 -->
<AlgorithmConfigModal
  v-model:visible="algorithmModalVisible"
  :mode="algorithmModalMode"
  :edit-data="algorithmEditData"
/>
```

### 修复5: `E2ETest.vue` — 移除不存在的解构

```typescript
// 修复前
const {
  // ...
  openEditAlgorithmModal,  // 不存在，移除
  // ...
} = useE2eView()
```

## 涉及文件

| 文件 | 修改类型 |
|------|----------|
| `frontend/src/composables/useAlgorithmSelection.ts` | 修正 API 端点、补充状态设置、参数改为可选 |
| `frontend/src/composables/useE2eView.ts` | 补充解构和导出、移除不存在的解构 |
| `frontend/src/views/APITestLogic/apiTest.ts` | 补充解构和导出 |
| `frontend/src/views/APITest.vue` | 使用状态变量替代内联表达式、补充解构 |
| `frontend/src/views/E2ETest.vue` | 移除不存在的解构 |

## 数据流修复示意

```
修复前:
  AlgorithmSelectionPanel @open-config(algo)
    → openAlgorithmConfigModal(algo)
      → editingAlgorithm = algo (简略数据)
      → algorithmModalMode = 未设置 (默认 'list')
      → algorithmEditData = 未设置 (默认 null)
    → AlgorithmConfigModal :mode='list' :edit-data=null  ❌ 列表模式，非编辑模式

修复后:
  AlgorithmSelectionPanel @open-config(algo)
    → openAlgorithmConfigModal(algo)
      → fetch /api/v1/algorithm/definitions/{algo.value}  ✅ 正确端点
      → editingAlgorithm = 完整算法定义数据
      → algorithmModalMode = 'edit'                       ✅ 设置模式
      → algorithmEditData = 完整算法定义数据               ✅ 设置编辑数据
    → AlgorithmConfigModal :mode='edit' :edit-data=完整数据  ✅ 编辑模式，参数CRUD可用
```
