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

### 返回参数组装为 [{field_code, field_value}] 格式

后端返回的 `CaseAlgorithmParam` 列表定义了表单有哪些字段。前端 DynamicForm 收集用户填写值后，
需将参数组装为 `[{field_code, field_value}]` 数组格式提交给后端：

```typescript
// 用户填写完成后，将表单值组装为 algorithmParams 数组格式
function buildAlgorithmParams(formValues: Record<string, any>): Array<{field_code: string; field_value: any}> {
  return Object.entries(formValues)
    .filter(([_, value]) => value !== null && value !== undefined)
    .map(([paramCode, value]) => ({
      field_code: paramCode,
      field_value: value,
    }));
}
```

### API 单记录 / E2E 双记录提交结构差异

- **API 测试用例（单记录）**：提交时 `rounds[i].algorithmParams` 只包含一条记录的参数数组
  ```json
  {
    "rounds": [
      {
        "algorithmParams": [
          {"field_code": "inputText", "field_value": "你好"},
          {"field_code": "inputAudio", "field_value": "audio_001"}
        ]
      }
    ]
  }
  ```

- **E2E 测试用例（双记录）**：提交时包含主记录和参考记录，每条记录各有独立的 `algorithmParams` 数组
  ```json
  {
    "rounds": [
      {
        "mainRecord": {
          "algorithmParams": [
            {"field_code": "railDistance", "field_value": 50},
            {"field_code": "volumeLevel", "field_value": 80}
          ]
        },
        "referenceRecord": {
          "algorithmParams": [
            {"field_code": "railDistance", "field_value": 50}
          ]
        }
      }
    ]
  }
  ```

### testcasesApi 扩展
```typescript
export const testcasesApi = {
  // ... 现有方法 ...
  
  // 新增：按 test_type 过滤
  getAll: (filters?: { algorithmType?: string; testType?: string; groupId?: string }) => {
    const params = new URLSearchParams();
    if (filters?.algorithmType) params.append('algorithm_type', filters.algorithmType);
    if (filters?.testType) params.append('test_type', filters.testType);
    if (filters?.groupId) params.append('group_id', filters.groupId);
    return api.get(`/testcases?${params.toString()}`);
  },
};
```

### evaluationApi 扩展
```typescript
export const evaluationApi = {
  // ... 现有方法 ...
  
  // 新增：支持 llm_judge 维度
  createDimension: (data: DimensionData) => {
    return api.post('/evaluation/dimensions', data);
  },
};
```

## 相关文档
- [01_选算法/backend/06_algorithm_Schema与Controller.md](backend/06_algorithm_Schema与Controller.md)
- [02_选用例/backend/05_testcase_controller双记录CRUD.md](../02_选用例/backend/05_testcase_controller双记录CRUD.md)
