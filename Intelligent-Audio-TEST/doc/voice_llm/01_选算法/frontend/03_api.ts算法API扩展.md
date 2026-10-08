# 03 - api.ts 算法 API 扩展

## 涉及文件
- `Intelligent-Audio-TEST/frontend/src/utils/api.ts`

## 现状分析
`api.ts` 包含所有后端 API 调用封装，当前包含：
- `algorithmApi` — 算法定义/参数/映射管理
- `testcasesApi` — 用例 CRUD
- `evaluationApi` — 评估维度管理

## 改造方案

### algorithmApi 扩展
```typescript
export const algorithmApi = {
  // ... 现有方法 ...
  
  // 新增：按 scope 过滤获取用例参数
  getCaseParams: (algorithmType: string, scope?: string) => {
    const params = scope ? `?algorithm_type=${algorithmType}&scope=${scope}` : `?algorithm_type=${algorithmType}`;
    return api.get(`/algorithm/case-params${params}`);
  },
};
```

### 格式转换职责

`[{field_code, field_value}]` 数组格式的转换**不在 api.ts 中处理**，而是由 RoundConfigEditor 组件在提交时完成。

DynamicForm 输出扁平字典 `Record<string, any>`，RoundConfigEditor 负责将其转换为数组格式后存入 `rounds[].algorithmParams`。

### testcasesApi 扩展
```typescript
export const testcasesApi = {
  // ... 现有方法 ...
  
  // 支持按 test_type 过滤（通过通用 params 传递）
  getAll: (params: Record<string, any>) => {
    return api.get('/testcases', { params });
  },
};
```

### evaluationApi 扩展
```typescript
export const evaluationApi = {
  // ... 现有方法 ...
  
  // 支持 llm_judge 维度
  createDimension: (data: DimensionData) => {
    return api.post('/evaluation/dimensions', data);
  },
};
```

## 相关文档
- [01_选算法/backend/06_algorithm_Schema与Controller.md](backend/06_algorithm_Schema与Controller.md)
- [02_选用例/backend/05_testcase_controller双记录CRUD.md](../02_选用例/backend/05_testcase_controller双记录CRUD.md)
