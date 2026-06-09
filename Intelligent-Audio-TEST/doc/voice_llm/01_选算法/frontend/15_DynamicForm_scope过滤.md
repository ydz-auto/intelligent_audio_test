# 15 - DynamicForm scope 过滤

## 涉及文件
- `Intelligent-Audio-TEST/frontend/src/components/algorithm/DynamicForm.vue`

## 现状分析
DynamicForm 组件根据 CaseAlgorithmParam 列表渲染动态表单。当前直接展示所有参数，无 scope 过滤。

## 改造方案

### 新增 Props
```typescript
interface Props {
  params: CaseAlgorithmParam[];
  modelValue: Array<{field_code: string; field_value: any}>;  // [{field_code, field_value}] 数组格式
  scope?: 'api' | 'e2e';  // 新增：当前 test_type
}
```

> **modelValue 格式**：`modelValue` 为 `[{field_code, field_value}]` 数组格式，而非 `Record<string, any>` 扁平字典。
> 每个元素包含 `field_code`（对应 `param_code`）和 `field_value`（用户填写的值）。
> 例如：`[{field_code: 'railDistance', field_value: 50}, {field_code: 'volumeLevel', field_value: 80}]`。

> **backgroundNoise 不在 DynamicForm 中渲染**：`backgroundNoise` 属于 round 级别字段（带 `loop` 属性），
> 不在 DynamicForm 的参数列表中渲染，而是在 RoundConfigEditor 中作为 round 级别字段单独处理。

### 过滤逻辑
```typescript
const filteredParams = computed(() => {
  if (!props.scope) return props.params;
  
  return props.params.filter(param => {
    // 显示条件：scope='common' 或 scope 匹配当前 test_type
    return param.scope === 'common' || param.scope === props.scope;
  });
});
```

### 显示规则

| param.scope | test_type='api' | test_type='e2e' | 无 scope 传入 |
|-------------|:---------------:|:---------------:|:-------------:|
| common | 显示 | 显示 | 显示 |
| api | 显示 | 隐藏 | 显示 |
| e2e | 隐藏 | 显示 | 显示 |

## 相关文档
- [01_选算法/backend/02_CaseAlgorithmParam_scope字段.md](backend/02_CaseAlgorithmParam_scope字段.md)
- [02_选用例/frontend/06_CaseForm_test_type驱动.md](../02_选用例/frontend/06_CaseForm_test_type驱动.md)
