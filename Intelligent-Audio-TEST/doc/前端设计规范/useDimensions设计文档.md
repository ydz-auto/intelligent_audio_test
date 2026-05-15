# useDimensions Composable 设计文档

## 概述

`useDimensions` 是一个 Vue 3 Composable，用于统一管理评测维度的数据获取、缓存和过滤。

## 背景问题

之前各组件独立调用 `evaluationApi.getAll()` 获取评测维度，存在以下问题：

1. **分页数据不完整** - 后端接口默认 `per_page=10`，只返回第一页数据
2. **重复请求** - 多个组件同时加载维度时造成重复网络请求
3. **缓存缺失** - 每次调用都重新请求，没有缓存机制
4. **前端过滤效率低** - 先查所有维度，再在前端按算法类型过滤

## 解决方案

创建统一的 `useDimensions` composable，提供：
- 自动分页获取所有维度
- 内存缓存（5分钟有效期）
- 按算法类型获取关联维度（新接口）

## 文件位置

```
frontend/src/composables/useDimensions.ts
```

## API

### 函数签名

```typescript
export function useDimensions()
```

### 返回值

| 属性 | 类型 | 说明 |
|------|------|------|
| `dimensions` | `Ref<EvaluationDimension[]>` | 缓存的维度数据 |
| `isLoading` | `Ref<boolean>` | 加载状态 |
| `fetchAllDimensions` | `function` | 获取所有维度（自动分页） |
| `fetchDimensionsByAlgorithmType` | `function` | 按算法类型获取关联维度 |
| `getDimensionsByAlgorithmType` | `function` | 从缓存中按算法类型过滤维度 |
| `clearCache` | `function` | 清除缓存 |

### fetchAllDimensions

```typescript
async function fetchAllDimensions(options?: {
  forceRefresh?: boolean  // 是否强制刷新（跳过缓存）
  categoryId?: number     // 按分类ID过滤
  search?: string         // 搜索关键词
}): Promise<EvaluationDimension[]>
```

**实现逻辑：**
1. 检查缓存是否有效（未过期且有数据）
2. 循环分页请求，每页 200 条
3. 按 ID 去重后存入缓存
4. 返回完整维度列表

### fetchDimensionsByAlgorithmType

```typescript
async function fetchDimensionsByAlgorithmType(algorithmType: string): Promise<EvaluationDimension[]>
```

调用后端新接口 `GET /api/v1/evaluation/dimensions/options?algorithm_type=xxx`，直接获取指定算法关联的维度。

### getDimensionsByAlgorithmType

```typescript
function getDimensionsByAlgorithmType(algorithmType: string): EvaluationDimension[]
```

从缓存中过滤关联了指定算法类型的维度（已废弃，推荐使用 `fetchDimensionsByAlgorithmType`）。

## 后端接口

### 新增接口：获取维度选项

`GET /api/v1/evaluation/dimensions/options`

| 参数 | 类型 | 说明 |
|------|------|------|
| algorithm_type | string | 可选，按算法类型过滤 |

**响应：**
```json
{
  "success": true,
  "data": {
    "dimensions": [
      {
        "id": 1,
        "name": "翻译质量",
        "description": "评估翻译质量",
        "type": "auto",
        "dimension_type": "main",
        "category_id": 1,
        "task_type_code": "bleu"
      }
    ]
  }
}
```

### 已有接口：获取所有维度（分页）

`GET /api/v1/evaluation/dimensions`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| per_page | int | 10 | 每页数量 |
| category_id | int | - | 分类ID过滤 |
| search | string | - | 搜索关键词 |

## 使用示例

### 基础使用（获取所有维度）

```typescript
import { useDimensions } from '@/composables/useDimensions'

const { fetchAllDimensions, dimensions } = useDimensions()

const allDimensions = await fetchAllDimensions()
```

### 按算法类型获取关联维度（推荐）

```typescript
import { useDimensions } from '@/composables/useDimensions'

const { fetchDimensionsByAlgorithmType } = useDimensions()

const translationDims = await fetchDimensionsByAlgorithmType('translation')
```

### 强制刷新

```typescript
const { fetchAllDimensions } = useDimensions()
const dimensions = await fetchAllDimensions({ forceRefresh: true })
```

## 已接入组件

| 组件 | 文件路径 | 使用方式 |
|------|----------|----------|
| TestCaseModal | `frontend/src/components/common/test-case/TestCaseModal.vue` | `fetchDimensionsByAlgorithmType` |
| AlgorithmConfigModal | `frontend/src/components/algorithm/AlgorithmConfigModal.vue` | `fetchAllDimensions` |
| useTestCaseConfig | `frontend/src/composables/useTestCaseConfig.ts` | `fetchAllDimensions` |

## 未接入组件

| 组件 | 原因 |
|------|------|
| EvaluationLogic/evaluation.ts | 评测维度列表页，需要分页搜索功能，直接调用 `evaluationApi.getAll(params)` 更合适 |

## 缓存机制

- **缓存时间**：5 分钟
- **缓存Key**：仅 dimensions 数据
- **去重**：按维度 ID 去重，保留首次出现的数据
- **强制刷新**：通过 `forceRefresh: true` 跳过缓存

## 注意事项

1. 缓存是模块级共享，所有使用该 composable 的组件共享同一份缓存
2. 当维度数据更新后，可调用 `clearCache()` 清除缓存
3. 建议在需要获取所有维度的场景使用，如表单选择、配置等
4. 列表分页等需要搜索功能的场景，仍直接调用 `evaluationApi.getAll(params)`
5. 按算法类型过滤维度时，优先使用 `fetchDimensionsByAlgorithmType`（后端过滤，效率更高）
