# 09_useDimensionConfig 扁平维度

> 文件：`frontend/src/components/common/test-case/TestCaseModal/useDimensionConfig.ts`

## 现状分析

useDimensionConfig（191行）管理评测维度的选择和配置。当前维度按 `{api, e2e}` 嵌套结构组织：

```ts
// 状态
const currentDimensionType = ref<'api' | 'e2e'>('api')  // 当前编辑的维度类型

// 函数签名
function openDimensionSelectModal(type: 'api' | 'e2e', index?: number)
function addAPIDimension()
function removeAPIDimension(index: number)
function addE2EDimension()
function removeE2EDimension(index: number)

// 维度配置存储结构
formData.config.dimensions = {
  api: DimensionConfig[],   // API 维度列表
  e2e: DimensionConfig[]    // E2E 维度列表
}
```

### 核心函数

| 函数 | 行号 | 用途 |
|------|------|------|
| `loadDimensions` | 15-37 | 加载所有维度或按算法类型加载 |
| `toggleDimensionSelection` | 60-74 | 切换维度选中状态（默认 weight=50, threshold=80） |
| `handleDimensionSelect` | 82-97 | 处理维度选择结果 |
| `convertDimensionIdsToObjects` | 125-145 | ID 字符串转完整对象 |
| `updateAssociatedDimensions` | 147-167 | 获取算法关联维度 |

## 改造方案

### 1. 移除 api/e2e 区分

```ts
// 移除 currentDimensionType
// const currentDimensionType = ref<'api' | 'e2e'>('api')  // 删除

// 新增 test_type 参数
export function useDimensionConfig(testType: Ref<'api' | 'e2e'>) {
```

### 2. 维度配置改为扁平数组

```ts
// 改造后
formData.config.dimensions = DimensionConfig[]   // 扁平数组

// 简化的维度操作函数
function addDimension() {
  dimensions.value.push({
    id: '',
    name: '',
    weight: 50,
    threshold: 80
  })
}

function removeDimension(index: number) {
  dimensions.value.splice(index, 1)
}
```

### 3. 移除 api/e2e 专用函数

删除以下函数：
- `addAPIDimension()` — 改为统一的 `addDimension()`
- `removeAPIDimension()` — 改为统一的 `removeDimension()`
- `addE2EDimension()` — 改为统一的 `addDimension()`
- `removeE2EDimension()` — 改为统一的 `removeDimension()`

### 4. openDimensionSelectModal 简化

```ts
// 改造后
function openDimensionSelectModal(index?: number) {
  // 不再需要 type 参数
  showDimensionModal.value = true
  currentDimensionIndex.value = index ?? -1
}
```

### 5. 加载关联维度不变

```ts
// updateAssociatedDimensions 不变
async function updateAssociatedDimensions(algorithmType: string) {
  const dims = await fetchDimensionsByAlgorithmType(algorithmType)
  associatedDimensions.value = dims
}
```

### 6. convertDimensionIdsToObjects 适配

```ts
// 改造后：处理扁平数组
function convertDimensionIdsToObjects(dimensionIds: string[]): DimensionConfig[] {
  return dimensionIds.map(id => {
    const found = availableDimensions.value.find(d => d.id === id || d.name === id)
    return found
      ? { id: found.id, name: found.name, weight: 50, threshold: 80 }
      : { id, name: id, weight: 50, threshold: 80 }
  })
}
```

## 不变部分

- `loadDimensions` — 加载维度列表
- `filteredAvailableDimensions` — 过滤可用维度
- `filteredDimensions` — 搜索过滤
- `isDimensionSelected` — 检查是否已选
- `toggleDimensionSelection` — 切换选择（默认值不变）
- `dimensionSearchQuery` — 搜索状态

## 引用关系

- ← `02_选用例/frontend/01_types.ts新接口定义` — DimensionConfig 接口
- ← `02_选用例/frontend/06_CaseForm_test_type驱动` — CaseForm 调用 useDimensionConfig
- → `02_选用例/frontend/06_CaseForm_test_type驱动` — 维度展示在 CaseForm 中
