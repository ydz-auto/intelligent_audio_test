# 15 - DynamicForm scope 过滤

## 涉及文件
- `Intelligent-Audio-TEST/frontend/src/components/algorithm/DynamicForm.vue`

## 现状分析
DynamicForm 组件根据 CaseAlgorithmParam 列表渲染动态表单。当前直接展示所有参数，无 scope 过滤。

## 改造方案

### 新增 Props
```typescript
interface Props {
  schema: FormSchema
  initialValues?: Record<string, any>
  disabled?: boolean
  showGroupHeader?: boolean
  defaultExpandedGroups?: string[]
  labelWidth?: string
  scope?: 'api' | 'e2e'  // 新增：当前 test_type
}
```

> **modelValue 格式**：`modelValue` 为 `Record<string, any>` 扁平字典格式（如 `{railDistance: 50, volumeLevel: 80}`），
> 而非 `[{field_code, field_value}]` 数组格式。格式转换由 RoundConfigEditor 在提交时处理。

> **backgroundNoise 不在 DynamicForm 中渲染**：`backgroundNoise` 属于 round 级别字段（带 `loop` 属性），
> 不在 DynamicForm 的参数列表中渲染，而是在 RoundConfigEditor 中作为 round 级别字段单独处理。

### 过滤逻辑
```typescript
const filterByScope = (fields: FieldSchema[]): FieldSchema[] => {
  if (!props.scope) return fields
  return fields.filter(f => !f.scope || f.scope === 'common' || f.scope === props.scope)
}
```

### 显示规则

| param.scope | test_type='api' | test_type='e2e' | 无 scope 传入 |
|-------------|:---------------:|:---------------:|:-------------:|
| common | 显示 | 显示 | 显示 |
| api | 显示 | 隐藏 | 显示 |
| e2e | 隐藏 | 显示 | 显示 |

### 格式转换（RoundConfigEditor 中处理）

DynamicForm 输出扁平字典，RoundConfigEditor 在提交时将其转换为 `[{field_code, field_value}]` 数组格式：

```typescript
// RoundConfigEditor 中的转换逻辑
function toAlgorithmParams(formValues: Record<string, any>): AlgorithmParamItem[] {
  return Object.entries(formValues)
    .filter(([_, value]) => value !== null && value !== undefined && value !== '')
    .map(([field_code, field_value]) => ({ field_code, field_value }))
}
```

## 相关文档
- [01_选算法/backend/02_CaseAlgorithmParam_scope字段.md](backend/02_CaseAlgorithmParam_scope字段.md)
- [02_选用例/frontend/06_CaseForm_test_type驱动.md](../02_选用例/frontend/06_CaseForm_test_type驱动.md)
